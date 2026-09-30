"""multi-system-reference / java-hardened-client task 1 -- Java gRPC mTLS
channel credentials (`com.harpia.runtime.grpc.HarpiaGrpcTls`).

The Java target generated gRPC stubs but had no way to open a channel a
hardened harpia server accepts: that server requires AND verifies a client
certificate and maps its CN to an RBAC role (`USAGE.md` §8). This task ships
`GradleAdapter/runtime/HarpiaGrpcTls.java`, the Java counterpart of the C++
`harpia::grpc_transport::channel_credentials()`, and proves it against the
**generated C++ `GrpcServer`**, not a Java server, because the reference
system's clients (Android + JVM) talk to a C++ server.

Two layers:
  - structural / pure Python (always): the runtime ships verbatim into the
    generated Java tree and never falls back to plaintext.
  - toolchain-gated (C++ gRPC toolchain + openssl AND gradle+JDK, i.e. the
    harpia Docker image): a C++ server process with mTLS + RBAC, and a Java
    client process calling `push` over a real socket:
        CA-signed cert, CN -> main   -> OK
        CA-signed cert, CN -> guest  -> PERMISSION_DENIED (the Java cert's CN
                                        reached the RBAC gate)
        no client cert               -> UNAUTHENTICATED from the RBAC gate (see
                                        below: the fixture is a mixed-mode project)
        cert from a foreign CA       -> UNAVAILABLE (handshake refused)
        null PEM streams             -> SecurityRefused, no channel opened

Why "no client cert" is refused by the gate and not by the handshake: the
shared `HarpiaTest` fixture has an `open` message (`reception_desk`), so its
generated bring-up is mixed mode (`kClientCertRequired = false`, see
`Database/CLAUDE.md`, `auth_gate.transport_mode()`). The TLS handshake
therefore admits a certless client, and the per-message RBAC gate on the
protected `users` service refuses it (`UNAUTHENTICATED`, detail
"unauthenticated"). A project with no `open` message requires the cert at the
handshake; the foreign-CA case below exercises handshake-level refusal here.

    Docker/run.sh pytest UnitTests/test_java_grpc_mtls.py
"""
import os
import subprocess
import sys

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(HERE)
RUNTIME_SRC = os.path.join(REPO_ROOT, "GradleAdapter", "runtime", "HarpiaGrpcTls.java")

if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

from UnitTests._java_gradle_helpers import generate, build_and_classpath  # noqa: E402
from UnitTests._java_grpc_server_helpers import (  # noqa: E402
    HASH, HAS_TOOLCHAIN, SKIP_REASON, build_server, provision, client_pair,
    running_server)


def _read(path):
    with open(path, encoding="utf-8") as f:
        return f.read()


# --------------------------------------------------------------------------
# structural -- pure Python, always runs
# --------------------------------------------------------------------------

def test_runtime_shipped_verbatim(tmp_path):
    out = generate(tmp_path, lang="java")
    shipped = os.path.join(out, "java", "src", "main", "java", "com", "harpia",
                           "runtime", "grpc", "HarpiaGrpcTls.java")
    assert os.path.isfile(shipped)
    assert _read(shipped) == _read(RUNTIME_SRC)


def test_runtime_is_fail_safe():
    src = _read(RUNTIME_SRC)
    assert "class SecurityRefused" in src
    assert "TlsChannelCredentials" in src
    # never degrades to plaintext
    assert "Insecure" not in src


# --------------------------------------------------------------------------
# toolchain-gated -- C++ gRPC server + Java client
# --------------------------------------------------------------------------

_toolchain = pytest.mark.skipif(not HAS_TOOLCHAIN, reason=SKIP_REASON)


_PROBE_JAVA = """\
package smoke;

import com.harpia.generated.users;
import com.harpia.generated.users_Message;
import com.harpia.generated.users_ServiceGrpc;
import com.harpia.runtime.grpc.HarpiaGrpcTls;
import com.google.protobuf.Descriptors.FieldDescriptor;
import io.grpc.ChannelCredentials;
import io.grpc.Grpc;
import io.grpc.ManagedChannel;
import io.grpc.StatusRuntimeException;
import io.grpc.TlsChannelCredentials;
import java.io.File;
import java.io.FileInputStream;
import java.util.concurrent.TimeUnit;

// args: mode host port ca cert key id
//   mode = mtls | nocert | nullcheck
// prints exactly one "RESULT <x>" line.
public class TlsProbe {
    public static void main(String[] a) throws Exception {
        String mode = a[0];
        if (mode.equals("nullcheck")) {
            try {
                HarpiaGrpcTls.credentials(null, null, null);
                System.out.println("RESULT NOT_REFUSED");
            } catch (HarpiaGrpcTls.SecurityRefused e) {
                System.out.println("RESULT REFUSED");
            }
            return;
        }
        String host = a[1];
        int port = Integer.parseInt(a[2]);
        ChannelCredentials creds = mode.equals("nocert")
            ? TlsChannelCredentials.newBuilder().trustManager(new File(a[3])).build()
            : HarpiaGrpcTls.credentials(new FileInputStream(a[3]),
                                        new FileInputStream(a[4]),
                                        new FileInputStream(a[5]));
        ManagedChannel ch = Grpc.newChannelBuilderForAddress(host, port, creds).build();
        try {
            users.Builder u = users.newBuilder();
            FieldDescriptor id = users.getDescriptor().findFieldByName("ID_{h}");
            long idValue = Long.parseLong(a[6]);
            u.setField(id, id.getJavaType() == FieldDescriptor.JavaType.LONG
                           ? (Object) idValue : (Object) (int) idValue);
            u.setField(users.getDescriptor().findFieldByName("name"), "neo");
            users_ServiceGrpc.newBlockingStub(ch)
                .withDeadlineAfter(8, TimeUnit.SECONDS)
                .push(users_Message.newBuilder().setMsg(u).build());
            System.out.println("RESULT OK");
        } catch (StatusRuntimeException e) {
            System.out.println("DETAIL " + e.getStatus().getDescription()
                               + " | cause=" + e.getStatus().getCause());
            System.out.println("RESULT " + e.getStatus().getCode());
        } finally {
            ch.shutdownNow().awaitTermination(5, TimeUnit.SECONDS);
        }
    }
}
"""


@pytest.fixture(scope="module")
def env(tmp_path_factory):
    tmp = str(tmp_path_factory.mktemp("harpia_java_grpc_mtls"))
    server_bin = build_server(tmp)

    # PKI: ours (writer = main, viewer = guest) + a foreign CA
    pki = os.path.join(tmp, "pki")
    provision(pki, "writer", "viewer")
    foreign = os.path.join(tmp, "foreign_pki")
    provision(foreign, "writer")
    rbac_map = os.path.join(tmp, "rbac_map.txt")
    with open(rbac_map, "w", encoding="utf-8") as fh:
        fh.write("writer main\nviewer guest\n")

    java_out = generate(os.path.join(tmp, "java_gen"), lang="java")
    classpath = build_and_classpath(os.path.join(java_out, "java"), {
        "smoke/TlsProbe.java": _PROBE_JAVA.replace("{h}", HASH),
    })

    with running_server(server_bin, pki, {"HARPIA_RBAC_MAP": rbac_map}) as port:
        yield {"classpath": classpath, "port": port, "pki": pki, "foreign": foreign}


_next_id = [100]


def _probe(env, mode, pki=None, identity=None, with_detail=False):
    pki = pki or env["pki"]
    cert, key = client_pair(pki, identity)
    _next_id[0] += 1
    r = subprocess.run(
        ["java", "-cp", env["classpath"], "smoke.TlsProbe", mode, "localhost",
         str(env["port"]), os.path.join(env["pki"], "ca.pem"), cert, key,
         str(_next_id[0])],
        capture_output=True, text=True, timeout=120)
    line = next((l for l in r.stdout.splitlines() if l.startswith("RESULT ")), None)
    assert line, "probe printed no RESULT (rc={}):\n{}{}".format(
        r.returncode, r.stdout, r.stderr)
    if with_detail:
        detail = next((l for l in r.stdout.splitlines() if l.startswith("DETAIL ")), "")
        return line[len("RESULT "):], detail[len("DETAIL "):]
    return line[len("RESULT "):]


@_toolchain
def test_ca_signed_cert_with_main_role_is_allowed(env):
    # mtls_provision.sh names the FIRST identity client.pem
    assert _probe(env, "mtls") == "OK"


@_toolchain
def test_cn_reaches_rbac_guest_cannot_push(env):
    assert _probe(env, "mtls", identity="viewer") == "PERMISSION_DENIED"


@_toolchain
def test_no_client_cert_is_refused_by_rbac_gate(env):
    # mixed-mode fixture: TLS admits the certless client, the RBAC gate on the
    # protected users service refuses it (module docstring)
    code, detail = _probe(env, "nocert", with_detail=True)
    assert code == "UNAUTHENTICATED"
    assert detail.startswith("unauthenticated"), detail


@_toolchain
def test_foreign_ca_cert_is_refused_at_handshake(env):
    # same CN ("writer"), different CA: identity alone must not be enough
    assert _probe(env, "mtls", pki=env["foreign"]) == "UNAVAILABLE"


@_toolchain
def test_missing_pem_raises_security_refused(env):
    assert _probe(env, "nullcheck") == "REFUSED"
