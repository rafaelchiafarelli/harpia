// harpia static-fuzz-ci epic -- shared hand-rolled fuzz driver.
//
// One translation unit covers all three parser targets; the target is picked
// at COMPILE time with -DHARPIA_FUZZ_TARGET=json|xml|soap (see
// UnitTests/test_fuzz_parsers.py, which compiles one binary per target with
//   g++ -std=c++17 -O1 -g -fsanitize=address,undefined
//       -fno-sanitize-recover=all -DHARPIA_FUZZ_TARGET=<t> ...).
//
// Runtime shape (task 2 decision):
//   argv = <target> <corpus-dir> [iterations] [seed]
//     <target>      must match the compiled-in target (guards a stale binary)
//     <corpus-dir>  directory of checked-in seed files
//     [iterations]  total mutated calls  (default 5000, env HARPIA_FUZZ_ITERS)
//     [seed]        xorshift PRNG seed   (default 0x9E3779B9, env HARPIA_FUZZ_SEED)
//
// For each seed file the target is called once as-is, then a seeded (fully
// reproducible) bit-flip / truncate / duplicate / insert / swap mutator runs
// for `iterations` total calls. A parser returning `false` (input rejected) is
// NOT a failure -- only an AddressSanitizer / UBSan trip is, and the sanitizer
// aborts the process, which the pytest job reads as a non-zero exit. On a
// sanitizer death the current input is hex-dumped and the seed printed so the
// exact case can be replayed with HARPIA_FUZZ_SEED (see UnitTests/fuzz/README.md).
//
// The scratch message is a fixed descriptor built in-process from a
// FileDescriptorProto -- the driver has NO dependency on any generated
// .proto / .pb.cc, only on libprotobuf and the parser's runtime header.

#include <dirent.h>

#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <memory>
#include <string>
#include <vector>

#include <google/protobuf/descriptor.h>
#include <google/protobuf/descriptor.pb.h>
#include <google/protobuf/dynamic_message.h>
#include <google/protobuf/message.h>

// ---- compile-time target selection --------------------------------------
// -DHARPIA_FUZZ_TARGET=json|xml|soap. The HARPIA__<name> ids let `#if` compare
// the bare token; `json` / `xml` / `soap` themselves are never #defined, so
// there is no identifier clash with the rest of the TU.
#define HARPIA__json 1
#define HARPIA__xml  2
#define HARPIA__soap 3
#define HARPIA__CAT2(a, b) a##b
#define HARPIA__CAT(a, b) HARPIA__CAT2(a, b)
#define HARPIA__STR2(x) #x
#define HARPIA__STR(x) HARPIA__STR2(x)

#ifndef HARPIA_FUZZ_TARGET
#  error "define -DHARPIA_FUZZ_TARGET=json|xml|soap"
#endif
#define HARPIA_FUZZ_TARGET_ID   HARPIA__CAT(HARPIA__, HARPIA_FUZZ_TARGET)
#define HARPIA_FUZZ_TARGET_NAME  HARPIA__STR(HARPIA_FUZZ_TARGET)

#if HARPIA_FUZZ_TARGET_ID == HARPIA__json
#  include "serialize/harpia_serialize.h"   // harpia::serialize::detail::from_json
#elif HARPIA_FUZZ_TARGET_ID == HARPIA__xml
#  include "xml/harpia_xml.h"               // harpia::xml::from_xml
#elif HARPIA_FUZZ_TARGET_ID == HARPIA__soap
#  error "the soap fuzz target is delivered by static-fuzz-ci task 4"
#else
#  error "unknown HARPIA_FUZZ_TARGET (want json | xml | soap)"
#endif

// libasan hook: runs immediately before the sanitizer aborts.
extern "C" void __asan_set_death_callback(void (*callback)(void));

namespace {

using ::google::protobuf::Message;

// ---- scratch message ---------------------------------------------------
// A mix of a scalar of every wire-relevant cpp-type, a repeated string, bytes,
// and a nested + repeated-nested sub-message, so the parser's reflection walk
// is meaningfully exercised without pulling in a generated type.
const ::google::protobuf::Descriptor* build_scratch_descriptor() {
    using ::google::protobuf::FieldDescriptorProto;
    using ::google::protobuf::FileDescriptorProto;

    static ::google::protobuf::DescriptorPool pool;

    FileDescriptorProto file;
    file.set_name("harpia_fuzz_scratch.proto");
    file.set_syntax("proto3");

    auto add = [](::google::protobuf::DescriptorProto* m, const char* name,
                  int number, FieldDescriptorProto::Type type,
                  bool repeated = false, const char* type_name = nullptr) {
        auto* f = m->add_field();
        f->set_name(name);
        f->set_number(number);
        f->set_type(type);
        f->set_label(repeated ? FieldDescriptorProto::LABEL_REPEATED
                              : FieldDescriptorProto::LABEL_OPTIONAL);
        if (type_name) f->set_type_name(type_name);
    };

    auto* inner = file.add_message_type();
    inner->set_name("FuzzInner");
    add(inner, "x", 1, FieldDescriptorProto::TYPE_STRING);
    add(inner, "y", 2, FieldDescriptorProto::TYPE_INT32);

    auto* m = file.add_message_type();
    m->set_name("FuzzMsg");
    add(m, "s1", 1, FieldDescriptorProto::TYPE_STRING);
    add(m, "i1", 2, FieldDescriptorProto::TYPE_INT32);
    add(m, "i2", 3, FieldDescriptorProto::TYPE_INT64);
    add(m, "d1", 4, FieldDescriptorProto::TYPE_DOUBLE);
    add(m, "b1", 5, FieldDescriptorProto::TYPE_BOOL);
    add(m, "u1", 6, FieldDescriptorProto::TYPE_UINT64);
    add(m, "rs", 7, FieldDescriptorProto::TYPE_STRING, /*repeated=*/true);
    add(m, "by", 8, FieldDescriptorProto::TYPE_BYTES);
    add(m, "inner", 9, FieldDescriptorProto::TYPE_MESSAGE, false, ".FuzzInner");
    add(m, "ri", 10, FieldDescriptorProto::TYPE_MESSAGE, true, ".FuzzInner");

    const auto* fd = pool.BuildFile(file);
    if (!fd) {
        std::fprintf(stderr, "fuzz: DescriptorPool::BuildFile failed\n");
        std::abort();
    }
    return fd->FindMessageTypeByName("FuzzMsg");
}

::google::protobuf::DynamicMessageFactory g_factory;
const Message* g_prototype = nullptr;

// ---- the target -------------------------------------------------------
// Every parser entry point is a clean `bool f(const std::string&, Message*)`
// with no socket. A `false` return is a rejected input, not a failure.
bool target_run(const std::string& in) {
    std::unique_ptr<Message> msg(g_prototype->New());
#if HARPIA_FUZZ_TARGET_ID == HARPIA__json
    return ::harpia::serialize::detail::from_json(in, msg.get());
#elif HARPIA_FUZZ_TARGET_ID == HARPIA__xml
    return ::harpia::xml::from_xml(in, msg.get());
#endif
}

// ---- reproducible PRNG (xorshift64*) --------------------------------
struct Rng {
    uint64_t s;
    explicit Rng(uint64_t seed)
        : s(seed ? seed : 0x9E3779B97F4A7C15ULL) {}
    uint64_t next() {
        s ^= s >> 12;
        s ^= s << 25;
        s ^= s >> 27;
        return s * 0x2545F4914F6CDD1DULL;
    }
    uint32_t below(uint32_t n) { return n ? static_cast<uint32_t>(next() % n) : 0; }
};

// ---- mutator --------------------------------------------------------
// bit flip / byte set / truncate / duplicate-slice / byte insert / byte swap.
// Growth is capped so the loop stays cheap and bounded.
std::string mutate(const std::string& base, Rng& rng) {
    static const size_t kMaxLen = 1u << 16;
    std::string b = base;
    const int rounds = 1 + static_cast<int>(rng.below(6));
    for (int r = 0; r < rounds; ++r) {
        if (b.empty()) {
            b.push_back(static_cast<char>(rng.next()));
            continue;
        }
        switch (rng.below(6)) {
            case 0:  // flip one bit
                b[rng.below(b.size())] ^= static_cast<char>(1u << rng.below(8));
                break;
            case 1:  // set one byte
                b[rng.below(b.size())] = static_cast<char>(rng.next());
                break;
            case 2:  // truncate
                b.resize(rng.below(static_cast<uint32_t>(b.size()) + 1));
                break;
            case 3: {  // duplicate a slice in place
                if (b.size() >= kMaxLen) break;
                const size_t p = rng.below(static_cast<uint32_t>(b.size()));
                const size_t n = 1 + rng.below(static_cast<uint32_t>(b.size() - p));
                b.insert(p, b.substr(p, n));
                break;
            }
            case 4:  // insert one byte
                if (b.size() >= kMaxLen) break;
                b.insert(b.begin() + rng.below(static_cast<uint32_t>(b.size()) + 1),
                         static_cast<char>(rng.next()));
                break;
            case 5: {  // swap two bytes
                std::swap(b[rng.below(static_cast<uint32_t>(b.size()))],
                          b[rng.below(static_cast<uint32_t>(b.size()))]);
                break;
            }
        }
    }
    return b;
}

// ---- crash reporting ----------------------------------------------
std::string g_current_input;
uint64_t g_seed = 0;
long g_iter = -1;
const char* g_phase = "init";

void hexdump(const std::string& s) {
    std::fprintf(stderr, "\n---- offending input (%zu bytes) ----\n", s.size());
    for (size_t i = 0; i < s.size(); i += 16) {
        std::fprintf(stderr, "%08zx  ", i);
        for (size_t j = 0; j < 16; ++j) {
            if (i + j < s.size())
                std::fprintf(stderr, "%02x ", static_cast<unsigned char>(s[i + j]));
            else
                std::fprintf(stderr, "   ");
        }
        std::fprintf(stderr, " |");
        for (size_t j = 0; j < 16 && i + j < s.size(); ++j) {
            const unsigned char c = static_cast<unsigned char>(s[i + j]);
            std::fprintf(stderr, "%c", (c >= 32 && c < 127) ? c : '.');
        }
        std::fprintf(stderr, "|\n");
    }
    std::fprintf(stderr,
                 "---- replay: HARPIA_FUZZ_SEED=0x%llx  "
                 "(target=%s phase=%s iter=%ld) ----\n\n",
                 static_cast<unsigned long long>(g_seed),
                 HARPIA_FUZZ_TARGET_NAME, g_phase, g_iter);
}

void on_death() { hexdump(g_current_input); }

std::string read_file(const std::string& path) {
    std::string data;
    FILE* f = std::fopen(path.c_str(), "rb");
    if (!f) return data;
    char buf[4096];
    size_t n;
    while ((n = std::fread(buf, 1, sizeof buf, f)) > 0) data.append(buf, n);
    std::fclose(f);
    return data;
}

}  // namespace

int main(int argc, char** argv) {
    __asan_set_death_callback(&on_death);

    if (argc < 3) {
        std::fprintf(stderr,
                     "usage: %s <target> <corpus-dir> [iterations] [seed]\n"
                     "  <target> must be '%s' (this binary's compiled-in target)\n",
                     argv[0], HARPIA_FUZZ_TARGET_NAME);
        return 2;
    }
    if (std::strcmp(argv[1], HARPIA_FUZZ_TARGET_NAME) != 0) {
        std::fprintf(stderr,
                     "fuzz: requested target '%s' but this binary is '%s'\n",
                     argv[1], HARPIA_FUZZ_TARGET_NAME);
        return 2;
    }
    const char* corpus_dir = argv[2];

    long iters = 5000;
    if (const char* e = std::getenv("HARPIA_FUZZ_ITERS")) iters = std::atol(e);
    if (argc >= 4) iters = std::atol(argv[3]);
    if (iters < 0) iters = 0;

    uint64_t seed = 0x9E3779B9ULL;
    if (const char* e = std::getenv("HARPIA_FUZZ_SEED"))
        seed = std::strtoull(e, nullptr, 0);
    if (argc >= 5) seed = std::strtoull(argv[4], nullptr, 0);
    g_seed = seed;

    g_prototype = g_factory.GetPrototype(build_scratch_descriptor());
    if (!g_prototype) {
        std::fprintf(stderr, "fuzz: GetPrototype(FuzzMsg) returned null\n");
        return 2;
    }

    std::vector<std::string> corpus;
    if (DIR* d = opendir(corpus_dir)) {
        for (dirent* ent; (ent = readdir(d)) != nullptr;) {
            const std::string name = ent->d_name;
            if (name == "." || name == "..") continue;
            corpus.push_back(read_file(std::string(corpus_dir) + "/" + name));
        }
        closedir(d);
    } else {
        std::fprintf(stderr, "fuzz: cannot open corpus dir %s\n", corpus_dir);
        return 2;
    }
    if (corpus.empty()) {
        std::fprintf(stderr, "fuzz: no seed files in %s\n", corpus_dir);
        return 2;
    }

    // 1. every seed once, verbatim.
    g_phase = "seed";
    for (size_t i = 0; i < corpus.size(); ++i) {
        g_iter = static_cast<long>(i);
        g_current_input = corpus[i];
        (void)target_run(corpus[i]);
    }

    // 2. bounded, seeded mutation loop.
    g_phase = "mutate";
    Rng rng(seed);
    for (long i = 0; i < iters; ++i) {
        g_iter = i;
        const std::string& base = corpus[rng.below(static_cast<uint32_t>(corpus.size()))];
        const std::string in = mutate(base, rng);
        g_current_input = in;
        (void)target_run(in);
    }

    std::printf("ok: %s target, %zu seeds + %ld mutations, seed=0x%llx\n",
                HARPIA_FUZZ_TARGET_NAME, corpus.size(), iters,
                static_cast<unsigned long long>(seed));
    return 0;
}
