"""multi-system-reference / java-hardened-client task 2 -- Java bearer-session
client (`com.harpia.runtime.grpc.HarpiaSession`).

The client half of the transport-authn task 5 protocol (`USAGE.md` §8): issue a
token via `heartBeat` + `harpia-issue-session` metadata (returned as
`harpia-session-token` trailing metadata), attach `authorization: Bearer
<token>` to every call, and re-issue exactly once after an "invalid session
token" refusal. Proven against the generated **C++** `GrpcServer`.

Two layers:
  - structural / pure Python (always): the runtime ships verbatim next to
    HarpiaGrpcTls.
  - toolchain-gated (C++ gRPC toolchain + openssl AND gradle+JDK), one Java
    client process per case over a real mTLS socket, server with
    `HARPIA_SESSION_KEY` set and `HARPIA_SESSION_TTL=3`:
        writer (main) issues + pushes             -> OK, 1 token issued
        viewer (guest) issues                     -> stream OK, push PERMISSION_DENIED
        writer's token on the viewer's channel    -> push OK (the token, not the
                                                     cert, is the identity)
        token expires, withRetry(push)            -> OK after exactly 1 re-issue
        a forged token                            -> UNAUTHENTICATED
                                                     "invalid session token" (no
                                                     fall-through to the cert)
    and a second server WITHOUT `HARPIA_SESSION_KEY`:
        issue                                     -> SessionRefused (fail-safe)

    Docker/run.sh pytest UnitTests/test_java_session_client.py
"""
import os
import subprocess
import sys

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(HERE)
RUNTIME_SRC = os.path.join(REPO_ROOT, "GradleAdapter", "runtime", "HarpiaSession.java")

if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

from UnitTests._java_gradle_helpers import generate, build_and_classpath  # noqa: E402
from UnitTests._java_grpc_server_helpers import (  # noqa: E402
    HASH, HAS_TOOLCHAIN, SKIP_REASON, build_server, provision, client_pair,
    running_server)

_TTL = 3


def _read(path):
    with open(path, encoding="utf-8") as f:
        return f.read()


# --------------------------------------------------------------------------
# structural -- pure Python, always runs
# --------------------------------------------------------------------------

def test_runtime_shipped_verbatim(tmp_path):
    out = generate(tmp_path, lang="java")
    shipped = os.path.join(out, "java", "src", "main", "java", "com", "harpia",
                           "runtime", "grpc", "HarpiaSession.java")
    assert os.path.isfile(shipped)
    assert _read(shipped) == _read(RUNTIME_SRC)


def test_runtime_speaks_the_server_protocol():
    src = _read(RUNTIME_SRC)
    # the exact metadata names + refusal text the C++ gate uses (auth_gate.py)
    for needle in ('"harpia-issue-session"', '"harpia-session-token"',
                   '"authorization"', '"Bearer "', '"invalid session token"'):
        assert needle in src, needle
    gate = _read(os.path.join(REPO_ROOT, "Database", "auth_gate.py"))
    for needle in ('"harpia-issue-session"', '"harpia-session-token"',
                   '"authorization"', '"invalid session token"'):
        assert needle in gate, needle


# --------------------------------------------------------------------------
# toolchain-gated -- C++ gRPC server + Java client
# --------------------------------------------------------------------------

_toolchain = pytest.mark.skipif(not HAS_TOOLCHAIN, reason=SKIP_REASON)

_PROBE_JAVA = """\
package smoke;

import com.harpia.generated.users;
import com.harpia.generated.users_Message;
import com.harpia.generated.users_ServiceGrpc;
import com.harpia.generated.users_Stream;
import com.harpia.runtime.grpc.HarpiaGrpcTls;
import com.harpia.runtime.grpc.HarpiaSession;
import com.google.protobuf.Descriptors.FieldDescriptor;
import io.grpc.Grpc;
import io.grpc.ManagedChannel;
import io.grpc.StatusRuntimeException;
import java.io.FileInputStream;
import java.util.Iterator;
import java.util.concurrent.TimeUnit;

// args: mode port ca certA keyA certB keyB id
// prints exactly one "RESULT ..." line.
public class SessionProbe {
    static ManagedChannel channel(int port, String ca, String cert, String key) throws Exception {
        return Grpc.newChannelBuilderForAddress("localhost", port,
            HarpiaGrpcTls.credentials(new FileInputStream(ca), new FileInputStream(cert),
                                      new FileInputStream(key))).build();
    }

    static users_Message msg(long idValue) {
        users.Builder u = users.newBuilder();
        FieldDescriptor id = users.getDescriptor().findFieldByName("ID_{h}");
        u.setField(id, id.getJavaType() == FieldDescriptor.JavaType.LONG
                       ? (Object) idValue : (Object) (int) idValue);
        u.setField(users.getDescriptor().findFieldByName("name"), "neo");
        return users_Message.newBuilder().setMsg(u).build();
    }

    static users_ServiceGrpc.users_ServiceBlockingStub stub(ManagedChannel ch, HarpiaSession s) {
        return users_ServiceGrpc.newBlockingStub(ch).withInterceptors(s.interceptor())
            .withDeadlineAfter(8, TimeUnit.SECONDS);
    }

    static String code(StatusRuntimeException e) {
        return e.getStatus().getCode() + " " + e.getStatus().getDescription();
    }

    public static void main(String[] a) throws Exception {
        String mode = a[0];
        int port = Integer.parseInt(a[1]);
        long id = Long.parseLong(a[7]);
        ManagedChannel chA = channel(port, a[2], a[3], a[4]);
        ManagedChannel chB = channel(port, a[2], a[5], a[6]);
        try {
            switch (mode) {
                case "issue_push": {
                    HarpiaSession s = HarpiaSession.issue(chA, users_ServiceGrpc.getHeartBeatMethod());
                    stub(chA, s).push(msg(id));
                    System.out.println("RESULT OK ISSUES " + s.issueCount());
                    break;
                }
                case "guest": {
                    HarpiaSession s = HarpiaSession.issue(chA, users_ServiceGrpc.getHeartBeatMethod());
                    Iterator<users_Message> it = stub(chA, s).streamSrc(users_Stream.newBuilder().build());
                    while (it.hasNext()) it.next();
                    String push;
                    try { stub(chA, s).push(msg(id)); push = "OK"; }
                    catch (StatusRuntimeException e) { push = e.getStatus().getCode().toString(); }
                    System.out.println("RESULT STREAM_OK PUSH_" + push);
                    break;
                }
                case "token_over_guest": {
                    HarpiaSession mainSession =
                        HarpiaSession.issue(chA, users_ServiceGrpc.getHeartBeatMethod());
                    HarpiaSession onGuest = HarpiaSession.fromToken(
                        chB, users_ServiceGrpc.getHeartBeatMethod(), mainSession.token());
                    stub(chB, onGuest).push(msg(id));
                    System.out.println("RESULT OK");
                    break;
                }
                case "expire": {
                    HarpiaSession s = HarpiaSession.issue(chA, users_ServiceGrpc.getHeartBeatMethod());
                    Thread.sleep({ttl_ms} + 1500);
                    s.withRetry(() -> stub(chA, s).push(msg(id)));
                    System.out.println("RESULT OK ISSUES " + s.issueCount());
                    break;
                }
                case "forged": {
                    HarpiaSession s = HarpiaSession.fromToken(
                        chA, users_ServiceGrpc.getHeartBeatMethod(), "forged.token.value");
                    try {
                        stub(chA, s).push(msg(id));
                        System.out.println("RESULT OK");
                    } catch (StatusRuntimeException e) {
                        System.out.println("RESULT " + code(e));
                    }
                    break;
                }
                case "nokey": {
                    try {
                        HarpiaSession.issue(chA, users_ServiceGrpc.getHeartBeatMethod());
                        System.out.println("RESULT ISSUED");
                    } catch (HarpiaSession.SessionRefused e) {
                        System.out.println("RESULT REFUSED");
                    }
                    break;
                }
                default:
                    System.out.println("RESULT BAD_MODE");
            }
        } catch (StatusRuntimeException e) {
            System.out.println("RESULT " + code(e));
        } finally {
            chA.shutdownNow().awaitTermination(5, TimeUnit.SECONDS);
            chB.shutdownNow().awaitTermination(5, TimeUnit.SECONDS);
        }
    }
}
"""


@pytest.fixture(scope="module")
def built(tmp_path_factory):
    tmp = str(tmp_path_factory.mktemp("harpia_java_session"))
    server_bin = build_server(tmp)
    pki = os.path.join(tmp, "pki")
    provision(pki, "writer", "viewer")
    rbac_map = os.path.join(tmp, "rbac_map.txt")
    with open(rbac_map, "w", encoding="utf-8") as fh:
        fh.write("writer main\nviewer guest\n")
    java_out = generate(os.path.join(tmp, "java_gen"), lang="java")
    classpath = build_and_classpath(os.path.join(java_out, "java"), {
        "smoke/SessionProbe.java": _PROBE_JAVA.replace("{h}", HASH)
                                               .replace("{ttl_ms}", str(_TTL * 1000)),
    })
    return {"server": server_bin, "pki": pki, "rbac_map": rbac_map,
            "classpath": classpath}


@pytest.fixture(scope="module")
def sessions_on(built):
    env = {"HARPIA_RBAC_MAP": built["rbac_map"],
           "HARPIA_SESSION_KEY": "multi-system-reference-test-key",
           "HARPIA_SESSION_TTL": str(_TTL)}
    with running_server(built["server"], built["pki"], env) as port:
        yield port


@pytest.fixture(scope="module")
def sessions_off(built):
    with running_server(built["server"], built["pki"],
                        {"HARPIA_RBAC_MAP": built["rbac_map"]}) as port:
        yield port


_next_id = [500]


def _probe(built, port, mode, a="writer", b="viewer"):
    ca = os.path.join(built["pki"], "ca.pem")
    cert_a, key_a = client_pair(built["pki"], None if a == "writer" else a)
    cert_b, key_b = client_pair(built["pki"], b)
    _next_id[0] += 1
    r = subprocess.run(
        ["java", "-cp", built["classpath"], "smoke.SessionProbe", mode, str(port),
         ca, cert_a, key_a, cert_b, key_b, str(_next_id[0])],
        capture_output=True, text=True, timeout=120)
    line = next((l for l in r.stdout.splitlines() if l.startswith("RESULT ")), None)
    assert line, "probe printed no RESULT (rc={}):\n{}{}".format(
        r.returncode, r.stdout, r.stderr)
    return line[len("RESULT "):]


@_toolchain
def test_issue_then_push_with_token(built, sessions_on):
    assert _probe(built, sessions_on, "issue_push") == "OK ISSUES 1"


@_toolchain
def test_guest_token_can_stream_but_not_push(built, sessions_on):
    assert _probe(built, sessions_on, "guest", a="viewer") == "STREAM_OK PUSH_PERMISSION_DENIED"


@_toolchain
def test_token_not_cert_is_the_identity(built, sessions_on):
    # a main-role token presented over the guest's mTLS channel may push
    assert _probe(built, sessions_on, "token_over_guest") == "OK"


@_toolchain
def test_expired_token_reissued_exactly_once(built, sessions_on):
    assert _probe(built, sessions_on, "expire") == "OK ISSUES 2"


@_toolchain
def test_forged_token_refused_without_cert_fallthrough(built, sessions_on):
    # writer's cert alone would be allowed to push; the bad token must win
    assert _probe(built, sessions_on, "forged") == "UNAUTHENTICATED invalid session token"


@_toolchain
def test_no_session_key_server_side_is_refused(built, sessions_off):
    assert _probe(built, sessions_off, "nokey") == "REFUSED"
