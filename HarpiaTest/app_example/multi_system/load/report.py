#!/usr/bin/env python3
"""Aggregate a load run (multi-system-reference / load-harness task 3).

    report.py <out_dir> [--bucket S]

Reads every *.jsonl in <out_dir> (one per client, written by `edge --load` /
`handheld --load`, usually via spawn.py) and writes <out_dir>/summary.json and
<out_dir>/summary.md; the Markdown is also printed. Python 3 stdlib only.

What it reports:
  - per client kind and op: count, ok rate, ops/s (over the whole run),
    latency p50 / p95 / p99 / max in microseconds (nearest-rank percentiles);
  - errors grouped by gRPC code, and by kind/op/code;
  - per subscriber: samples received and the summed / largest sequence gap;
  - a timeline in --bucket-second slices (default 10) so ramp-up and
    saturation are visible;
  - clients: from spawn.json when spawn.py wrote one (exit codes, crashed).

Record formats (task 1):
  {"t","client_kind","identity","op","ok","grpc_code","latency_us"}
      op = session | create | list | read
  {"t","client_kind","identity","op":"sub_recv","seq_gap"}
A line that isn't JSON or lacks those keys is counted as malformed, not fatal:
a client killed mid-write leaves a partial last line.
"""
import argparse
import json
import math
import os
import sys

OP_KEYS = ("t", "client_kind", "identity", "op", "ok", "grpc_code", "latency_us")
SUB_KEYS = ("t", "client_kind", "identity", "op", "seq_gap")


def percentile(sorted_values, p):
    """Nearest-rank: the smallest value with at least p% of values <= it."""
    if not sorted_values:
        return 0
    k = max(1, int(math.ceil(p / 100.0 * len(sorted_values))))
    return sorted_values[k - 1]


def load(out_dir):
    ops, subs, files, malformed = [], [], 0, 0
    for name in sorted(os.listdir(out_dir)):
        if not name.endswith(".jsonl"):
            continue
        files += 1
        with open(os.path.join(out_dir, name), encoding="utf-8") as f:
            for line in f:
                if not line.strip():
                    continue
                try:
                    r = json.loads(line)
                except ValueError:
                    malformed += 1
                    continue
                if not isinstance(r, dict):
                    malformed += 1
                elif r.get("op") == "sub_recv" and all(k in r for k in SUB_KEYS):
                    subs.append(r)
                elif r.get("op") != "sub_recv" and all(k in r for k in OP_KEYS):
                    ops.append(r)
                else:
                    malformed += 1
    return ops, subs, files, malformed


def summarize(out_dir, bucket=10):
    ops, subs, files, malformed = load(out_dir)
    times = [r["t"] for r in ops] + [r["t"] for r in subs]
    t0 = min(times) if times else 0.0
    span = (max(times) - t0) if times else 0.0
    per_s = max(span, 1.0)   # a sub-second run reports per-op counts as /s

    by = {}
    for r in ops:
        by.setdefault(r["client_kind"], {}).setdefault(r["op"], []).append(r)
    kinds = {}
    for kind in sorted(by):
        kinds[kind] = {}
        for op in sorted(by[kind]):
            rs = by[kind][op]
            lat = sorted(int(r["latency_us"]) for r in rs)
            ok = sum(1 for r in rs if r["ok"])
            kinds[kind][op] = {
                "count": len(rs),
                "ok": ok,
                "ok_rate": round(ok / len(rs), 4),
                "ops_per_s": round(len(rs) / per_s, 3),
                "latency_us": {"p50": percentile(lat, 50), "p95": percentile(lat, 95),
                               "p99": percentile(lat, 99), "max": lat[-1]},
            }

    errors, errors_by = {}, {}
    for r in ops:
        if r["ok"]:
            continue
        code = r["grpc_code"]
        errors[code] = errors.get(code, 0) + 1
        key = "{}/{}/{}".format(r["client_kind"], r["op"], code)
        errors_by[key] = errors_by.get(key, 0) + 1

    subscribers = {}
    for r in subs:
        s = subscribers.setdefault(r["identity"], {"samples": 0, "seq_gap_total": 0, "seq_gap_max": 0})
        s["samples"] += 1
        s["seq_gap_total"] += int(r["seq_gap"])
        s["seq_gap_max"] = max(s["seq_gap_max"], int(r["seq_gap"]))

    timeline = []
    if times:
        n = int(span // bucket) + 1
        timeline = [{"t_s": i * bucket, "ops": 0, "ok": 0, "errors": 0, "sub_recv": 0,
                     "clients": set()} for i in range(n)]
        for r in ops:
            b = timeline[int((r["t"] - t0) // bucket)]
            b["ops"] += 1
            b["ok" if r["ok"] else "errors"] += 1
            b["clients"].add(r["identity"])
        for r in subs:
            timeline[int((r["t"] - t0) // bucket)]["sub_recv"] += 1
        for b in timeline:
            b["clients"] = len(b["clients"])

    clients = {"identities": len({r["identity"] for r in ops} | {r["identity"] for r in subs})}
    spawn = os.path.join(out_dir, "spawn.json")
    if os.path.exists(spawn):
        with open(spawn, encoding="utf-8") as f:
            sp = json.load(f)
        procs = sp.get("clients", [])
        clients.update({
            "spawned": len(procs),
            "crashed": sorted(c["identity"] for c in procs if c.get("crashed")),
            "exit_codes": {str(k): v for k, v in sorted(_count(c.get("exit_code") for c in procs).items(),
                                                        key=lambda kv: str(kv[0]))},
        })

    return {
        "files": files,
        "records": len(ops) + len(subs),
        "malformed": malformed,
        "duration_s": round(span, 3),
        "ops": kinds,
        "errors": dict(sorted(errors.items())),
        "errors_by_op": dict(sorted(errors_by.items())),
        "subscribers": dict(sorted(subscribers.items())),
        "timeline": timeline,
        "bucket_s": bucket,
        "clients": clients,
    }


def _count(values):
    out = {}
    for v in values:
        out[v] = out.get(v, 0) + 1
    return out


def markdown(s):
    L = ["# Load run summary", "",
         "{} files, {} records ({} malformed), {} s, {} identities".format(
             s["files"], s["records"], s["malformed"], s["duration_s"], s["clients"]["identities"])]
    c = s["clients"]
    if "spawned" in c:
        L.append("spawned {}, crashed {}{}".format(
            c["spawned"], len(c["crashed"]), (": " + ", ".join(c["crashed"])) if c["crashed"] else ""))
    L += ["", "## Operations", "",
          "| kind | op | count | ok rate | ops/s | p50 us | p95 us | p99 us | max us |",
          "|---|---|---:|---:|---:|---:|---:|---:|---:|"]
    for kind, ops in s["ops"].items():
        for op, o in ops.items():
            l = o["latency_us"]
            L.append("| {} | {} | {} | {:.4f} | {:.3f} | {} | {} | {} | {} |".format(
                kind, op, o["count"], o["ok_rate"], o["ops_per_s"], l["p50"], l["p95"], l["p99"], l["max"]))
    L += ["", "## Errors", ""]
    if s["errors"]:
        L += ["| kind/op/code | count |", "|---|---:|"]
        L += ["| {} | {} |".format(k, v) for k, v in s["errors_by_op"].items()]
    else:
        L.append("none")
    L += ["", "## Subscribers", ""]
    if s["subscribers"]:
        L += ["| identity | samples | seq gap total | seq gap max |", "|---|---:|---:|---:|"]
        L += ["| {} | {} | {} | {} |".format(k, v["samples"], v["seq_gap_total"], v["seq_gap_max"])
              for k, v in s["subscribers"].items()]
    else:
        L.append("none")
    L += ["", "## Timeline ({} s buckets)".format(s["bucket_s"]), "",
          "| t (s) | clients | ops | ok | errors | sub_recv |", "|---:|---:|---:|---:|---:|---:|"]
    L += ["| {} | {} | {} | {} | {} | {} |".format(b["t_s"], b["clients"], b["ops"], b["ok"], b["errors"],
                                                  b["sub_recv"]) for b in s["timeline"]]
    return "\n".join(L) + "\n"


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("out_dir")
    ap.add_argument("--bucket", type=int, default=10, help="timeline bucket in seconds (default 10)")
    a = ap.parse_args(argv)
    if not os.path.isdir(a.out_dir):
        print("report: no such directory: " + a.out_dir, file=sys.stderr)
        return 2
    s = summarize(a.out_dir, max(1, a.bucket))
    md = markdown(s)
    with open(os.path.join(a.out_dir, "summary.json"), "w", encoding="utf-8") as f:
        json.dump(s, f, indent=2, sort_keys=True)
        f.write("\n")
    with open(os.path.join(a.out_dir, "summary.md"), "w", encoding="utf-8") as f:
        f.write(md)
    sys.stdout.write(md)
    return 0


if __name__ == "__main__":
    sys.exit(main())
