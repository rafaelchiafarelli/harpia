"""python-target / tri-language-interop task 3: gRPC + REST cross-calls
between C++ and Python servers and C++, Java and Python clients, flat and
hardened.

Generations: the HarpiaTest fixture for Python (C++ + Python) under the
repo's hardened profile and under a low-risk one (``test_py_rest.
generate_low_risk``), plus one java generation (its stubs don't depend on
the profile). One mTLS PKI (``mtls_provision.sh``: ``main``, ``guest``) and
one role map (``main main`` / ``guest guest``) serve every case.

Servers, per profile: the generated C++ ``GrpcServer`` + ``HttpServer``
(one C++ peer process) and the generated Python ``HttpServer`` + gRPC.
Both bring-ups emit TLS under either profile (the fixture's ``protected``
message), so every client trusts the CA:

- **flat** (low-risk): server-authenticated TLS, no client certificate,
  ``users`` behind the flat ``x-user`` / ``x-pswd`` gate -- right
  credentials accepted (push / pullByID; POST / GET / DELETE), wrong ones
  refused (``UNAUTHENTICATED`` / 401);
- **hardened**: ``main`` creates but can't remove, ``guest`` reads only,
  a certless client is refused. The C++ servers and the Python
  ``HttpServer`` run mixed mode (the fixture's ``open`` message), so a
  certless caller gets ``UNAUTHENTICATED`` / 401 from the RBAC gate. The
  Python gRPC server is the generated ``users`` servicer on a
  client-cert-*required* server (``tls.grpc_server_credentials(..., True)``)
  -- the generated mixed-mode Python ``GrpcServer`` never sees a client
  certificate (NEXT_SESSION item 33), so a CN-based matrix can't run on it;
  a certless caller is refused at the handshake (``UNAVAILABLE``). gRPC has
  no remove RPC: "can't remove" is checked over REST;
- **sessions** (same ``HARPIA_SESSION_KEY`` everywhere): tokens issued by
  the C++ ``HttpServer`` (``POST /v1/session``), the Python ``HttpServer``
  and the C++ ``GrpcServer`` (``heartBeat``, issued by the Java
  ``HarpiaSession`` client) each work, from a certless client, on the
  *other* language's REST and gRPC servers (the Python gRPC side here is the
  generated mixed-mode ``GrpcServer``, which accepts bearer tokens -- item
  35); a tampered token is refused there;
- **capability** ``negotiate`` both ways on both transports: C++ and Python
  clients against the Python ``GrpcServer`` (registers the capability
  service) and a C++ ``capabilities_service`` server, and against a C++ and
  a Python HTTP ``/capabilities`` route (plain HTTP: both HTTP negotiate
  clients are plaintext). Java has no capability client in the Java target
  (``capabilities_service.proto`` isn't even copied into ``java/``) -- that
  is asserted, and Java is out of this bullet.

The Java client is ``multi-system-reference``'s hardened client
(``HarpiaGrpcTls`` / ``HarpiaSession``, on ``dev`` since V2) for gRPC and the
JDK ``HttpClient`` (a PKCS#12 of the client pair) for REST. C++ and Java
clients run as batch probes (tab-separated requests on stdin); the C++
REST client is a small OpenSSL one (``harpia_test_client.h`` is plaintext).
Gated on the C++ gRPC toolchain + crow/asio + SOCI, gradle + JDK, openssl
and the Python toolchain.
"""
import concurrent.futures
import glob
import http.client
import json
import os
import shutil
import socket
import ssl
import subprocess
import sys

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(HERE)
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

from UnitTests import _py_cpp_parity as P  # noqa: E402
from UnitTests import test_py_rbac as R  # noqa: E402
from UnitTests import test_py_sessions as S  # noqa: E402
from UnitTests._java_gradle_helpers import build_and_classpath, generate  # noqa: E402
from UnitTests._java_grpc_server_helpers import HAS_TOOLCHAIN  # noqa: E402
from UnitTests.test_py_rest import generate_low_risk  # noqa: E402

HASH = "3ac5d8b36fc7dcfb70888145147ddfb7"
PK = "ID_" + HASH
THIRD = os.path.join(REPO_ROOT, "third_party")
PROVISION = os.path.join(REPO_ROOT, "Assets", "cmake", "mtls_provision.sh")
FLAT = {"x-user": "users", "x-pswd": HASH}
BAD = {"x-user": "users", "x-pswd": "wrong"}
KEY = S.KEY
CLIENTS = ("cpp", "java", "python")
SERVERS = ("cpp", "python")

pytestmark = pytest.mark.skipif(
    not (HAS_TOOLCHAIN and R.HAVE_CPP_HTTP and P.HAVE_PY
         and os.path.exists("/usr/include/soci/soci.h")),
    reason="needs the C++ gRPC toolchain + crow/asio + SOCI, gradle+JDK, openssl "
           "and the Python toolchain (image)")


def _mod(path):
    import importlib
    return importlib.import_module(path.format(h=HASH))


def _free_port():
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


# -- PKI + generations ---------------------------------------------------------

@pytest.fixture(scope="module")
def pki(tmp_path_factory):
    d = tmp_path_factory.mktemp("x3_pki")
    p = subprocess.run(["sh", PROVISION, str(d), "localhost", "main", "guest"],
                       capture_output=True, text=True)
    assert p.returncode == 0, p.stdout + p.stderr
    out = {"ca": str(d / "ca.pem"), "cert": str(d / "server.pem"),
           "key": str(d / "server_key.pem"), None: ("-", "-")}
    for who in ("main", "guest"):
        cert, key = str(d / ("client_%s.pem" % who)), str(d / ("client_%s_key.pem" % who))
        p12 = str(d / ("client_%s.p12" % who))
        subprocess.run(["openssl", "pkcs12", "-export", "-in", cert, "-inkey", key,
                        "-out", p12, "-passout", "pass:harpia"], check=True,
                       capture_output=True)
        out[who] = (cert, key)
        out["p12", who] = p12
    out["p12", None] = "-"
    roles = d / "roles.map"
    roles.write_text("main main\nguest guest\n")
    out["roles"] = str(roles)
    return out


@pytest.fixture(scope="module")
def gens(tmp_path_factory):
    tmp = tmp_path_factory.mktemp("x3_gen")
    os.makedirs(str(tmp / "low" / "out"))
    return {"hardened": P.generate_python(str(tmp / "hard")),
            "flat": generate_low_risk(tmp / "low")}


# -- C++ peer: the generated servers, a capability server and a client ----------

_CPP = r'''
#include <chrono>
#include <cstdio>
#include <fstream>
#include <iostream>
#include <sstream>
#include <string>
#include <thread>
#include <vector>
#include <grpcpp/grpcpp.h>
#include <openssl/bio.h>
#include <openssl/err.h>
#include <openssl/ssl.h>
#include <soci/soci.h>
#include <soci/sqlite3/soci-sqlite3.h>
#include "grpc/grpc_server_bringup.h"
#include "http/http_server_bringup.h"
#include "db/users_@H@_crudl.h"
#include "db/reception_desk_@H@_crudl.h"
#include "capability/capabilities_@H@_grpc.h"
#include "capability/capabilities_@H@_http.h"
#include "capability/harpia_capability.h"
#include "capability/harpia_http_capability.h"
#include "protofiles/users_@H@_service.grpc.pb.h"

static std::string pem(const std::string& p) {
    std::ifstream f(p); std::stringstream s; s << f.rdbuf(); return s.str();
}

static std::string unhex(const std::string& h) {
    std::string out;
    for (size_t i = 0; i + 1 < h.size(); i += 2)
        out += static_cast<char>(std::stoi(h.substr(i, 2), nullptr, 16));
    return out;
}

static std::vector<std::string> split(const std::string& s, char sep) {
    std::vector<std::string> out;
    size_t start = 0, at;
    while ((at = s.find(sep, start)) != std::string::npos) {
        out.push_back(s.substr(start, at - start));
        start = at + 1;
    }
    out.push_back(s.substr(start));
    return out;
}

static bool seed(::soci::session& db) {
    harpia::db::users_dao dao(db);
    if (!dao.create_table()) return false;
    if (!harpia::db::reception_desk_dao(db).create_table()) return false;
    ::users u; u.set_id_@H@(1); u.set_name("neo");
    return dao.create(u);
}

static void wait_stdin() { std::string line; while (std::getline(std::cin, line)) {} }

// grpc <addr> <ca|-> <cert|-> <key|-> <metadata hex> <create|read> <id> -> status code
static std::string do_grpc(const std::vector<std::string>& p) {
    std::shared_ptr< ::grpc::ChannelCredentials> creds;
    ::grpc::SslCredentialsOptions o;
    o.pem_root_certs = pem(p[2]);
    if (p[3] != "-") { o.pem_cert_chain = pem(p[3]); o.pem_private_key = pem(p[4]); }
    creds = ::grpc::SslCredentials(o);
    auto stub = ::frameworkProtos::users_Service::NewStub(::grpc::CreateChannel(p[1], creds));
    ::grpc::ClientContext c;
    c.set_deadline(std::chrono::system_clock::now() + std::chrono::seconds(10));
    for (const auto& kv : split(unhex(p[5]), '\n')) {
        size_t at = kv.find(": ");
        if (at != std::string::npos) c.AddMetadata(kv.substr(0, at), kv.substr(at + 2));
    }
    ::grpc::Status st;
    if (p[6] == "create") {
        ::frameworkProtos::users_Message m;
        m.mutable_msg()->set_id_@H@(std::stoi(p[7]));
        m.mutable_msg()->set_name("from-cpp");
        ::frameworkProtos::errorCode out;
        st = stub->push(&c, m, &out);
    } else {
        ::frameworkProtos::users_ID id; id.set_id(std::stoi(p[7]));
        ::frameworkProtos::users_Message out;
        st = stub->pullByID(&c, id, &out);
    }
    return std::to_string(static_cast<int>(st.error_code()));
}

// rest <port> <ca> <cert|-> <key|-> <method> <path> <body hex> <headers hex> -> status (0: no TLS)
static std::string do_rest(const std::vector<std::string>& p) {
    SSL_CTX* ctx = SSL_CTX_new(TLS_client_method());
    SSL_CTX_load_verify_locations(ctx, p[2].c_str(), nullptr);
    SSL_CTX_set_verify(ctx, SSL_VERIFY_PEER, nullptr);
    if (p[3] != "-") {
        SSL_CTX_use_certificate_chain_file(ctx, p[3].c_str());
        SSL_CTX_use_PrivateKey_file(ctx, p[4].c_str(), SSL_FILETYPE_PEM);
    }
    BIO* bio = BIO_new_ssl_connect(ctx);
    SSL* ssl = nullptr;
    BIO_get_ssl(bio, &ssl);
    SSL_set_tlsext_host_name(ssl, "localhost");
    SSL_set1_host(ssl, "localhost");
    BIO_set_conn_hostname(bio, ("127.0.0.1:" + p[1]).c_str());
    std::string status = "0";
    if (BIO_do_connect(bio) == 1 && BIO_do_handshake(bio) == 1) {
        const std::string body = unhex(p[7]);
        std::string req = p[5] + " " + p[6] + " HTTP/1.1\r\nHost: localhost\r\n"
                          "Connection: close\r\nContent-Length: " + std::to_string(body.size()) +
                          "\r\n" + unhex(p[8]) + "\r\n" + body;
        BIO_write(bio, req.data(), static_cast<int>(req.size()));
        std::string resp;
        char buf[4096];
        int n;
        while ((n = BIO_read(bio, buf, sizeof buf)) > 0) resp.append(buf, n);
        if (resp.size() > 12 && resp.compare(0, 5, "HTTP/") == 0) status = resp.substr(9, 3);
    }
    BIO_free_all(bio);
    SSL_CTX_free(ctx);
    return status;
}

static std::string types(const std::optional<std::set<std::string>>& t, int legacy) {
    if (!t) return "LEGACY " + std::to_string(legacy);
    std::string out;
    for (const auto& s : *t) out += (out.empty() ? "" : ",") + s;
    return out;
}

int main(int argc, char** argv) {
    const std::string mode = argv[1];
    crow::logger::setLogLevel(crow::LogLevel::Critical);
    if (mode == "servers") {  // servers <grpc port> <http port> <ca> <cert> <key>
        ::soci::session gdb(::soci::sqlite3, ":memory:"), hdb(::soci::sqlite3, ":memory:");
        if (!seed(gdb) || !seed(hdb)) return 2;
        harpia::grpc_transport::GrpcServer gs(gdb, std::string("localhost:") + argv[2],
                                             harpia::grpc_transport::MtlsFiles{argv[4], argv[5], argv[6]});
        if (!gs.ok()) return 3;
        harpia::http_transport::HttpServer hs(hdb, "/v1", "/soap",
                                             harpia::http_transport::MtlsFiles{argv[4], argv[5], argv[6]});
        hs.app().bindaddr("127.0.0.1").port(std::stoi(argv[3])).multithreaded();
        std::thread t([&] { try { hs.app().run(); } catch (...) {} });
        hs.app().wait_for_server_start();
        std::cout << "READY" << std::endl;
        wait_stdin();
        hs.stop(); t.join(); gs.shutdown();
        return 0;
    }
    if (mode == "cap-servers") {  // cap-servers <http port>: plain gRPC + HTTP capability
        harpia::grpc_svc::capabilities_service cap;
        ::grpc::ServerBuilder b;
        int gport = 0;
        b.AddListeningPort("127.0.0.1:0", ::grpc::InsecureServerCredentials(), &gport);
        b.RegisterService(&cap);
        auto gs = b.BuildAndStart();
        crow::SimpleApp app;
        harpia::http_capability::register_capabilities(app, "/api/v1");
        app.bindaddr("127.0.0.1").port(std::stoi(argv[2]));
        std::thread t([&] { app.run(); });
        app.wait_for_server_start();
        std::cout << "READY " << gport << std::endl;
        wait_stdin();
        app.stop(); t.join(); gs->Shutdown();
        return 0;
    }
    // client: one tab-separated request per stdin line, one answer per line
    std::string line;
    while (std::getline(std::cin, line)) {
        const auto p = split(line, '\t');
        std::string out;
        int legacy = 0;
        if (p[0] == "grpc") out = do_grpc(p);
        else if (p[0] == "rest") out = do_rest(p);
        else if (p[0] == "capgrpc") {  // capgrpc <addr> <ca|->
            auto creds = p[2] == "-" ? ::grpc::InsecureChannelCredentials()
                                     : ::grpc::SslCredentials({pem(p[2]), "", ""});
            out = types(harpia::capability::negotiate(::grpc::CreateChannel(p[1], creds),
                                                      std::chrono::milliseconds(5000),
                                                      [&] { ++legacy; }), legacy);
        } else if (p[0] == "caphttp") {  // caphttp <port> <base>
            out = types(harpia::capability::negotiate("127.0.0.1", std::stoi(p[1]), p[2], 5000,
                                                      [&] { ++legacy; }), legacy);
        }
        std::printf("%s\n", out.c_str());
        std::fflush(stdout);
    }
    return argc > 0 ? 0 : 1;
}
'''


def _pkg(*names):
    return subprocess.run(["pkg-config", "--cflags", "--libs", *names], capture_output=True,
                          text=True, check=True).stdout.split()


@pytest.fixture(scope="module")
def cpp(gens, tmp_path_factory):
    """{profile: peer binary}. The protobuf / gRPC objects are compiled once
    (from the hardened tree -- the .proto files don't depend on the profile)."""
    work = tmp_path_factory.mktemp("x3_cpp")
    root = os.path.join(gens["hardened"], "generated", "cpp")
    cflags = ["-std=c++17", "-O0", "-DASIO_STANDALONE", "-DCROW_ENABLE_SSL",
              "-I", os.path.join(THIRD, "crow"), "-I", os.path.join(THIRD, "asio"),
              "-I", os.path.join(THIRD, "tinyxml2")]
    pkg = _pkg("grpc++", "protobuf")
    sources = sorted(glob.glob(os.path.join(root, "protofiles", "*.pb.cc")))
    sources.append(os.path.join(THIRD, "tinyxml2", "tinyxml2.cpp"))

    def compile_(args):
        src, obj, inc = args
        r = subprocess.run(["g++", *cflags, "-I", inc, *[f for f in pkg if f.startswith("-I")],
                            "-c", src, "-o", obj], capture_output=True, text=True, timeout=900)
        assert r.returncode == 0, "{}:\n{}".format(src, r.stderr[-4000:])
        return obj

    jobs = [(s, str(work / (os.path.basename(s) + ".o")), root) for s in sources]
    for profile, gen in gens.items():
        src = work / ("peer_%s.cpp" % profile)
        src.write_text(_CPP.replace("@H@", HASH))
        jobs.append((str(src), str(work / ("peer_%s.o" % profile)),
                     os.path.join(gen, "generated", "cpp")))
    with concurrent.futures.ThreadPoolExecutor(os.cpu_count() or 4) as ex:
        objs = list(ex.map(compile_, jobs))
    shared, out = objs[:len(sources)], {}
    for profile, main_obj in zip(gens, objs[len(sources):]):
        exe = str(work / ("peer_" + profile))
        r = subprocess.run(["g++", main_obj, *shared, "-o", exe, "-lsoci_core", "-lsoci_sqlite3",
                            *pkg, "-lssl", "-lcrypto", "-lpthread", "-ldl"],
                           capture_output=True, text=True, timeout=900)
        assert r.returncode == 0, r.stderr[-4000:]
        out[profile] = exe
    return out


class CppServers:
    def __init__(self, exe, pki, env):
        self.grpc, self.http = _free_port(), _free_port()
        self.proc = subprocess.Popen(
            [exe, "servers", str(self.grpc), str(self.http), pki["ca"], pki["cert"], pki["key"]],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True, env={**os.environ, **env})
        assert self.proc.stdout.readline().strip() == "READY"

    def stop(self):
        self.proc.stdin.close()
        self.proc.wait(timeout=30)


# -- Java client -----------------------------------------------------------------

_JAVA = r'''
package xlang;

import com.google.protobuf.Descriptors.FieldDescriptor;
import com.harpia.generated.users;
import com.harpia.generated.users_ID;
import com.harpia.generated.users_Message;
import com.harpia.generated.users_ServiceGrpc;
import com.harpia.runtime.grpc.HarpiaGrpcTls;
import com.harpia.runtime.grpc.HarpiaSession;
import io.grpc.ChannelCredentials;
import io.grpc.ClientInterceptors;
import io.grpc.Grpc;
import io.grpc.ManagedChannel;
import io.grpc.Metadata;
import io.grpc.StatusRuntimeException;
import io.grpc.TlsChannelCredentials;
import io.grpc.stub.MetadataUtils;
import java.io.BufferedReader;
import java.io.File;
import java.io.FileInputStream;
import java.io.InputStreamReader;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.charset.StandardCharsets;
import java.security.KeyStore;
import java.security.cert.CertificateFactory;
import java.time.Duration;
import java.util.concurrent.TimeUnit;
import javax.net.ssl.KeyManagerFactory;
import javax.net.ssl.SSLContext;
import javax.net.ssl.TrustManagerFactory;

// one tab-separated request per stdin line, one answer per line
public class TransportProbe {
    static String unhex(String h) {
        byte[] b = new byte[h.length() / 2];
        for (int i = 0; i < b.length; i++)
            b[i] = (byte) Integer.parseInt(h.substring(2 * i, 2 * i + 2), 16);
        return new String(b, StandardCharsets.UTF_8);
    }

    static ManagedChannel channel(String host, int port, String ca, String cert, String key)
            throws Exception {
        ChannelCredentials creds = cert.equals("-")
            ? TlsChannelCredentials.newBuilder().trustManager(new File(ca)).build()
            : HarpiaGrpcTls.credentials(new FileInputStream(ca), new FileInputStream(cert),
                                        new FileInputStream(key));
        return Grpc.newChannelBuilderForAddress(host, port, creds).build();
    }

    // grpc <host> <port> <ca> <cert|-> <key|-> <metadata hex> <create|read> <id>
    static String grpc(String[] p) throws Exception {
        ManagedChannel ch = channel(p[1], Integer.parseInt(p[2]), p[3], p[4], p[5]);
        try {
            Metadata md = new Metadata();
            for (String kv : unhex(p[6]).split("\n")) {
                int at = kv.indexOf(": ");
                if (at > 0)
                    md.put(Metadata.Key.of(kv.substring(0, at), Metadata.ASCII_STRING_MARSHALLER),
                           kv.substring(at + 2));
            }
            users_ServiceGrpc.users_ServiceBlockingStub stub = users_ServiceGrpc.newBlockingStub(
                ClientInterceptors.intercept(ch, MetadataUtils.newAttachHeadersInterceptor(md)))
                .withDeadlineAfter(10, TimeUnit.SECONDS);
            int id = Integer.parseInt(p[8]);
            if (p[7].equals("create")) {
                users.Builder u = users.newBuilder();
                u.setField(users.getDescriptor().findFieldByName("ID_@H@"), id);
                u.setField(users.getDescriptor().findFieldByName("name"), "from-java");
                stub.push(users_Message.newBuilder().setMsg(u).build());
            } else {
                stub.pullByID(users_ID.newBuilder().setId(id).build());
            }
            return "OK";
        } catch (StatusRuntimeException e) {
            return e.getStatus().getCode().name();
        } finally {
            ch.shutdownNow();
        }
    }

    // issue <host> <port> <ca> <cert> <key>: a session token from heartBeat
    static String issue(String[] p) throws Exception {
        ManagedChannel ch = channel(p[1], Integer.parseInt(p[2]), p[3], p[4], p[5]);
        try {
            return HarpiaSession.issue(ch, users_ServiceGrpc.getHeartBeatMethod()).token();
        } finally {
            ch.shutdownNow();
        }
    }

    // rest <port> <ca> <p12|-> <method> <path> <body hex> <headers hex>
    static String rest(String[] p) throws Exception {
        KeyStore trust = KeyStore.getInstance("PKCS12");
        trust.load(null, null);
        trust.setCertificateEntry("ca", CertificateFactory.getInstance("X.509")
            .generateCertificate(new FileInputStream(p[2])));
        TrustManagerFactory tmf =
            TrustManagerFactory.getInstance(TrustManagerFactory.getDefaultAlgorithm());
        tmf.init(trust);
        KeyManagerFactory kmf = null;
        if (!p[3].equals("-")) {
            KeyStore ks = KeyStore.getInstance("PKCS12");
            ks.load(new FileInputStream(p[3]), "harpia".toCharArray());
            kmf = KeyManagerFactory.getInstance(KeyManagerFactory.getDefaultAlgorithm());
            kmf.init(ks, "harpia".toCharArray());
        }
        SSLContext ssl = SSLContext.getInstance("TLS");
        ssl.init(kmf == null ? null : kmf.getKeyManagers(), tmf.getTrustManagers(), null);
        HttpClient client = HttpClient.newBuilder().sslContext(ssl)
            .version(HttpClient.Version.HTTP_1_1).connectTimeout(Duration.ofSeconds(10)).build();
        String body = unhex(p[6]);
        HttpRequest.Builder rb = HttpRequest.newBuilder(
                URI.create("https://localhost:" + p[1] + p[5]))
            .timeout(Duration.ofSeconds(10))
            .method(p[4], body.isEmpty() ? HttpRequest.BodyPublishers.noBody()
                                         : HttpRequest.BodyPublishers.ofString(body));
        for (String kv : unhex(p[7]).split("\r\n")) {
            int at = kv.indexOf(": ");
            if (at > 0) rb.header(kv.substring(0, at), kv.substring(at + 2));
        }
        try {
            return Integer.toString(
                client.send(rb.build(), HttpResponse.BodyHandlers.ofString()).statusCode());
        } catch (java.io.IOException e) {
            return "0";
        }
    }

    public static void main(String[] args) throws Exception {
        BufferedReader in = new BufferedReader(
            new InputStreamReader(System.in, StandardCharsets.UTF_8));
        String line;
        while ((line = in.readLine()) != null) {
            String[] p = line.split("\t", -1);
            String out;
            try {
                out = p[0].equals("grpc") ? grpc(p) : p[0].equals("rest") ? rest(p) : issue(p);
            } catch (Exception e) {
                out = "ERROR " + e;
            }
            System.out.println(out.replace('\n', ' '));
            System.out.flush();
        }
    }
}
'''


@pytest.fixture(scope="module")
def java(tmp_path_factory):
    gen = generate(tmp_path_factory.mktemp("x3_java"), lang="java")
    cp = build_and_classpath(os.path.join(gen, "java"),
                             {"xlang/TransportProbe.java": _JAVA.replace("@H@", HASH)})
    return {"gen": gen, "cp": cp}


# -- the three clients, one request shape ------------------------------------------
#
# ("grpc", port, who, metadata, op, id) -> status code name
# ("rest", port, who, method, path, body, headers) -> HTTP status (0: refused at TLS)

def _hex(s):
    return s.encode().hex()


def _md_text(md):
    return "\n".join("%s: %s" % kv for kv in md.items())


def _hdr_text(hdr):
    return "".join("%s: %s\r\n" % kv for kv in hdr.items())


def run_clients(lang, reqs, pki, tool=None):
    """``tool``: the C++ peer binary or the Java classpath."""
    if lang == "python":
        return [_py_request(r, pki) for r in reqs]
    lines = []
    for r in reqs:
        cert, key = pki[r[2]]
        if r[0] == "grpc" and lang == "cpp":
            lines.append(["grpc", "localhost:%d" % r[1], pki["ca"], cert, key,
                          _hex(_md_text(r[3])), r[4], str(r[5])])
        elif r[0] == "grpc":
            lines.append(["grpc", "localhost", str(r[1]), pki["ca"], cert, key,
                          _hex(_md_text(r[3])), r[4], str(r[5])])
        elif lang == "cpp":
            lines.append(["rest", str(r[1]), pki["ca"], cert, key, r[3], r[4], _hex(r[5]),
                          _hex(_hdr_text(r[6]))])
        else:
            lines.append(["rest", str(r[1]), pki["ca"], pki["p12", r[2]], r[3], r[4],
                          _hex(r[5]), _hex(_hdr_text(r[6]))])
    cmd = [tool, "client"] if lang == "cpp" else ["java", "-cp", tool, "xlang.TransportProbe"]
    out = subprocess.run(cmd, input="".join("\t".join(x) + "\n" for x in lines),
                         capture_output=True, text=True, timeout=600)
    assert out.returncode == 0, out.stderr[-3000:]
    got = out.stdout.splitlines()
    assert len(got) == len(reqs), out.stdout[-2000:] + out.stderr[-2000:]
    if lang == "cpp":
        import grpc
        names = {c.value[0]: c.name for c in grpc.StatusCode}
        got = [names[int(g)] if r[0] == "grpc" else int(g) for r, g in zip(reqs, got)]
    else:
        got = [g if r[0] == "grpc" else int(g) for r, g in zip(reqs, got)]
    return got


def _py_request(r, pki):
    import grpc
    if r[0] == "grpc":
        tls = _mod("harpia_runtime.tls")
        if r[2] is None:
            creds = grpc.ssl_channel_credentials(root_certificates=open(pki["ca"], "rb").read())
        else:
            creds = tls.grpc_channel_credentials(tls.MtlsFiles(pki["ca"], *pki[r[2]]))
        ch = grpc.secure_channel("localhost:%d" % r[1], creds)
        stub = _mod("harpia_generated.protofiles.users_{h}_service_pb2_grpc").users_ServiceStub(ch)
        svc = _mod("harpia_generated.protofiles.users_{h}_service_pb2")
        md = tuple(r[3].items())
        try:
            if r[4] == "create":
                m = svc.users_Message()
                setattr(m.msg, PK, r[5])
                m.msg.name = "from-python"
                stub.push(m, metadata=md, timeout=10)
            else:
                stub.pullByID(svc.users_ID(id=r[5]), metadata=md, timeout=10)
            return "OK"
        except grpc.RpcError as e:
            return e.code().name
        finally:
            ch.close()
    ctx = ssl.create_default_context(cafile=pki["ca"])
    if r[2] is not None:
        ctx.load_cert_chain(*pki[r[2]])
    try:
        return R._request(r[1], ctx, r[3], r[4], r[5].encode() or None, r[6])[0]
    except (ssl.SSLError, ConnectionError):
        return 0


def _user_json(pk, name):
    m = _mod("harpia_generated.protofiles.users_{h}_pb2").users()
    setattr(m, PK, pk)
    m.name = name
    return _mod("harpia_runtime.json").to_json(m)


# -- Python servers --------------------------------------------------------------

def _py_pool(tmp_path):
    pool = _mod("harpia_runtime.db.pool").sqlite_pool(str(tmp_path / "py.db"), size=4)
    with pool.borrow() as conn:
        dao = _mod("harpia_generated.db.users_{h}_dao").users_dao(conn)
        dao.create_table()
        u = _mod("harpia_generated.protofiles.users_{h}_pb2").users(name="neo")
        setattr(u, PK, 1)
        dao.create(u)
        _mod("harpia_generated.db.reception_desk_{h}_dao").reception_desk_dao(conn).create_table()
    return pool


class PyServers:
    """The generated Python ``HttpServer`` + a gRPC server over one pool.
    ``grpc="bringup"``: the generated ``GrpcServer``; ``"certs-required"``:
    the generated ``users`` servicer on a client-cert-required server."""

    def __init__(self, pki, tmp_path, grpc_kind):
        import grpc
        tls = _mod("harpia_runtime.tls")
        files = tls.MtlsFiles(pki["ca"], pki["cert"], pki["key"])
        pool = _py_pool(tmp_path)
        self.http_srv = _mod("harpia_generated.http.http_server_bringup").HttpServer(
            pool, host="localhost", rest_base="/v1", soap_base="/soap", mtls=files)
        self.http_srv.start()
        self.http = self.http_srv.port
        if grpc_kind == "bringup":
            self.grpc_srv = _mod("harpia_generated.grpc.grpc_server_bringup").GrpcServer(
                pool, "localhost:0", mtls=files)
            self.grpc_srv.start()
            self.grpc, self._stop_grpc = self.grpc_srv.port, self.grpc_srv.stop
        else:
            mod = _mod("harpia_generated.grpc.users_{h}_grpc")
            server = grpc.server(concurrent.futures.ThreadPoolExecutor(max_workers=4))
            mod.add_to_server(mod.users_Service(pool), server)
            self.grpc = server.add_secure_port(
                "localhost:0", tls.grpc_server_credentials(True, files, True))
            server.start()
            self._stop_grpc = lambda: server.stop(None).wait()

    def stop(self):
        self.http_srv.stop()
        self._stop_grpc()


def _arm_python(gen, pki, monkeypatch, tmp_path, session_key=None):
    P.fixture_messages(P.py_root(gen))  # activate this generation
    R._arm(pki["roles"], monkeypatch)
    rev = tmp_path / "revoked.txt"
    rev.write_text("")
    S._configure(monkeypatch, session_key, str(rev))
    return str(rev)


# -- flat profile -------------------------------------------------------------------

def _flat_requests(ports, base):
    g, h = ports
    js = {"Content-Type": "application/json"}
    return [
        (("grpc", g, None, FLAT, "create", base), "OK"),
        (("grpc", g, None, FLAT, "read", 1), "OK"),
        (("grpc", g, None, BAD, "create", base + 1), "UNAUTHENTICATED"),
        (("grpc", g, None, BAD, "read", 1), "UNAUTHENTICATED"),
        (("grpc", g, None, {}, "read", 1), "UNAUTHENTICATED"),
        (("rest", h, None, "POST", "/v1/users", _user_json(base + 2, "flat"),
          {**js, "X-User": "users", "X-Pswd": HASH}), 201),
        (("rest", h, None, "GET", "/v1/users/%d" % (base + 2), "",
          {"X-User": "users", "X-Pswd": HASH}), 200),
        (("rest", h, None, "DELETE", "/v1/users/%d" % (base + 2), "",
          {"X-User": "users", "X-Pswd": HASH}), 204),
        (("rest", h, None, "GET", "/v1/users/1", "", {"X-User": "users", "X-Pswd": "x"}), 401),
        (("rest", h, None, "POST", "/v1/users", _user_json(base + 3, "flat"), js), 401),
    ]


def test_flat_profile(gens, cpp, java, pki, monkeypatch, tmp_path):
    _arm_python(gens["flat"], pki, monkeypatch, tmp_path)
    bring = _mod("harpia_generated.grpc.grpc_server_bringup")
    assert (bring.EMIT_TLS, bring.CLIENT_CERT_REQUIRED) == (True, False)
    servers = {"cpp": CppServers(cpp["flat"], pki, {}),
               "python": PyServers(pki, tmp_path, "bringup")}
    try:
        for s, srv in servers.items():
            for k, client in enumerate(CLIENTS):
                cases = _flat_requests((srv.grpc, srv.http), 1000 * (k + 1))
                got = run_clients(client, [r for r, _ in cases], pki,
                                  cpp["flat"] if client == "cpp" else java["cp"])
                assert got == [w for _, w in cases], (s, client)
    finally:
        for srv in servers.values():
            srv.stop()


# -- hardened profile ---------------------------------------------------------------

_WANT = {  # who -> (grpc create, grpc read, REST create, REST read, REST remove)
    "main": ("OK", "OK", 201, 200, 403),
    "guest": ("PERMISSION_DENIED", "OK", 403, 200, 403),
}


def _hardened_requests(server, ports, base):
    g, h = ports
    js = {"Content-Type": "application/json"}
    cases = []
    for k, who in enumerate(("main", "guest", None)):
        pk = base + 10 * k
        if who is None:
            refused = "UNAUTHENTICATED" if server == "cpp" else "UNAVAILABLE"
            want = (refused, refused, 401, 401, 401)
        else:
            want = _WANT[who]
        cases += [
            (("grpc", g, who, {}, "create", pk), want[0]),
            (("grpc", g, who, {}, "read", 1), want[1]),
            (("rest", h, who, "POST", "/v1/users", _user_json(pk + 1, "hard"), js), want[2]),
            (("rest", h, who, "GET", "/v1/users/1", "", {}), want[3]),
            (("rest", h, who, "DELETE", "/v1/users/1", "", {}), want[4]),
        ]
    return cases


def test_hardened_profile(gens, cpp, java, pki, monkeypatch, tmp_path):
    _arm_python(gens["hardened"], pki, monkeypatch, tmp_path)
    servers = {"cpp": CppServers(cpp["hardened"], pki, {"HARPIA_RBAC_MAP": pki["roles"]}),
               "python": PyServers(pki, tmp_path, "certs-required")}
    try:
        for s, srv in servers.items():
            for k, client in enumerate(CLIENTS):
                cases = _hardened_requests(s, (srv.grpc, srv.http), 1000 * (k + 1))
                got = run_clients(client, [r for r, _ in cases], pki,
                                  cpp["hardened"] if client == "cpp" else java["cp"])
                assert got == [w for _, w in cases], (s, client)
    finally:
        for srv in servers.values():
            srv.stop()


# -- sessions: a token from one server language works on the other ------------------

def test_session_tokens_cross_languages(gens, cpp, java, pki, monkeypatch, tmp_path):
    rev = _arm_python(gens["hardened"], pki, monkeypatch, tmp_path, session_key=KEY)
    env = {"HARPIA_RBAC_MAP": pki["roles"], "HARPIA_SESSION_KEY": KEY,
           "HARPIA_SESSION_REVOCATIONS": rev}
    cpp_srv = CppServers(cpp["hardened"], pki, env)
    py_srv = PyServers(pki, tmp_path, "bringup")  # mixed mode: bearer tokens work here
    sc = _mod("harpia_runtime.session_client")
    try:
        main = ssl.create_default_context(cafile=pki["ca"])
        main.load_cert_chain(*pki["main"])
        tokens = {"cpp-rest": S._token_over_http(cpp_srv.http, main),
                  "python-rest": S._token_over_http(py_srv.http, main)}
        issued = subprocess.run(
            ["java", "-cp", java["cp"], "xlang.TransportProbe"], capture_output=True, text=True,
            timeout=120, input="\t".join(["issue", "localhost", str(cpp_srv.grpc), pki["ca"],
                                          *pki["main"]]) + "\n")
        tokens["cpp-grpc"] = issued.stdout.strip()
        assert tokens["cpp-grpc"].startswith("v1."), issued.stdout + issued.stderr
        js = {"Content-Type": "application/json"}
        for k, (origin, token) in enumerate(sorted(tokens.items())):
            other = py_srv if origin.startswith("cpp") else cpp_srv
            bearer = sc.bearer_header(token)
            forged = sc.bearer_header(token[:-1] + ("A" if token[-1] != "A" else "B"))
            pk = 5000 + 10 * k
            cases = [
                (("grpc", other.grpc, None, {"authorization": bearer["Authorization"]},
                  "create", pk), "OK"),
                (("grpc", other.grpc, None, {"authorization": forged["Authorization"]},
                  "read", 1), "UNAUTHENTICATED"),
                (("rest", other.http, None, "POST", "/v1/users", _user_json(pk + 1, "tok"),
                  {**js, **bearer}), 201),
                (("rest", other.http, None, "GET", "/v1/users/1", "", forged), 401),
            ]
            got = run_clients("python", [r for r, _ in cases], pki)
            assert got == [w for _, w in cases], origin
    finally:
        py_srv.stop()
        cpp_srv.stop()


# -- capability negotiate -------------------------------------------------------------

def test_capability_negotiate_both_transports(gens, cpp, java, pki, monkeypatch, tmp_path):
    _arm_python(gens["hardened"], pki, monkeypatch, tmp_path)
    want = sorted(_mod("harpia_generated.capability.capabilities_{h}_grpc").MESSAGE_TYPES)
    http_port = _free_port()
    proc = subprocess.Popen([cpp["hardened"], "cap-servers", str(http_port)],
                            stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True)
    ready, cpp_grpc = proc.stdout.readline().split()
    assert ready == "READY"
    py = PyServers(pki, tmp_path, "bringup")  # the generated GrpcServer registers it
    router_mod = _mod("harpia_runtime.http.router")
    router = router_mod.Router()
    _mod("harpia_generated.capability.capabilities_{h}_http").register_capabilities(
        router, "/api/v1")
    py_http = router_mod.Server(router)
    py_http.start()
    try:
        lines = [["capgrpc", "localhost:%d" % py.grpc, pki["ca"]],
                 ["capgrpc", "127.0.0.1:%s" % cpp_grpc, "-"],
                 ["caphttp", str(py_http.port), "/api/v1"],
                 ["caphttp", str(http_port), "/api/v1"]]
        out = subprocess.run([cpp["hardened"], "client"], timeout=120, capture_output=True,
                             text=True, input="".join("\t".join(x) + "\n" for x in lines))
        assert [o.split(",") for o in out.stdout.splitlines()] == [want] * 4, out.stdout

        import grpc
        cap_grpc, cap_http = (_mod("harpia_runtime.capability.grpc"),
                              _mod("harpia_runtime.capability.http"))
        legacy = []
        for ch in (grpc.secure_channel("localhost:%d" % py.grpc, grpc.ssl_channel_credentials(
                       root_certificates=open(pki["ca"], "rb").read())),
                   grpc.insecure_channel("127.0.0.1:%s" % cpp_grpc)):
            try:
                assert sorted(cap_grpc.negotiate(ch, 5.0, on_legacy_peer=legacy.append)) == want
            finally:
                ch.close()
        for port in (py_http.port, http_port):
            assert sorted(cap_http.negotiate("127.0.0.1", port, "/api/v1", 5.0,
                                             on_legacy_peer=legacy.append)) == want
        assert legacy == []
    finally:
        py_http.stop()
        py.stop()
        proc.stdin.close()
        proc.wait(timeout=30)

    # Java: no capability client in the Java target (out of this bullet)
    java_root = os.path.join(java["gen"], "java")
    assert not glob.glob(os.path.join(java_root, "**", "capabilities_service*"), recursive=True)
    assert not glob.glob(os.path.join(java_root, "**", "*apabilit*.java"), recursive=True)
