"""message-level-hardening initiative, protected-open-modifiers epic, task 3
-- per-message REST/SOAP/gRPC gating.

Before this task, `Database/auth_gate.py`'s RBAC-vs-flat choice and the
REST+SOAP/gRPC mTLS bring-up were both a single project-wide boolean
(`transport_hardening_required(compliance)`). This task makes the gate
per-message (`auth_gate.effective_rbac()`): a `protected` message always gets
the RBAC gate, an `open` message always gets the flat gate, regardless of the
project default; a message using neither inherits the project default
unchanged. `auth_gate.transport_mode()` derives the whole-project transport
shape (`emit_tls`/`client_cert_required`) this needs when a message's
effective gate diverges from the project default -- see task 2's confirmed
mTLS-optional-mode finding.

Deliberately NOT covered here (per the epic's task 3 scope and
Database/auth_gate.py's own docstring): composition. A message's own
`is_protected`/`is_open` is the only input to its own gate -- composing an
unprotected message inside a protected one does not propagate anything, in
either direction. That is a schema-author decision, not something harpia
infers or blocks.

  - Unit: `effective_rbac()` / `transport_mode()` truth tables, directly.
  - Structural (pure Python, via RestAdapter/SoapAdapter/GrpcServiceAdapter
    driven with stub message objects -- the same pattern
    test_rest_soap_mtls.py's test_hardening_flag_follows_compliance uses):
    a project where no message's effective_rbac() diverges from the project
    default (this includes every project using neither modifier anywhere)
    renders the exact byte-identical bring-up call site that existed before
    this task; a divergent project renders the new kEmitTls/
    kClientCertRequired constants and routes each message to the correct
    gate variant, and copies the RBAC/session runtime whenever ANY message
    needs it (not just when the whole project is hardened).

Reuses test_rbac.py's stub-message + adapter.Process() + read-the-emitted-
text harness pattern rather than building a new one, per the task's own
instruction -- the underlying RBAC/flat gate MECHANISMS (harpia_rbac.h's
decide(), the flat X-User/X-Pswd check) are unchanged and already proven by
test_rbac.py / test_stage11_soap.py / test_stage12_rest.py / test_stage13.py;
what's new and worth testing here is which mechanism gets ROUTED to which
message.
"""
import json
import os

from Compliance.http_common import HTTP_OUT_SUBDIR
from Compliance.rbac_common import RBAC_RUNTIME
from Compliance.session_common import SESSION_RUNTIME
from Compliance.grpc_common import GRPC_MTLS_RUNTIME
from Crypto.backend import get_backend
from Compliance.context import ComplianceContext, PhiHandling, RiskClass, Topology
from Database.auth_gate import effective_rbac, transport_mode

HARDENED = ComplianceContext(risk_class=RiskClass.CLASS_C,
                             topology=Topology.CLOUD_CONNECTED,
                             phi_handling=PhiHandling.NONE, jurisdiction=[])
OPEN_PROFILE = ComplianceContext(risk_class=RiskClass.CLASS_A,
                                 topology=Topology.STANDALONE,
                                 phi_handling=PhiHandling.NONE, jurisdiction=[])


def _read(path):
    with open(path, encoding="utf-8") as f:
        return f.read()


class _Msg:
    """Stub table-bearing message, same shape test_rest_soap_mtls.py's
    test_hardening_flag_follows_compliance uses -- adapters only read
    name/md5Hash/isEnum/tableName/variables plus (this task) is_protected/
    is_open off a message, never construct a real Message.Process() output."""
    isEnum = False
    variables = []

    def __init__(self, name, is_protected=False, is_open=False):
        self.name = name
        self.md5Hash = "deadbeef"
        self.tableName = name + "_table"
        self.is_protected = is_protected
        self.is_open = is_open


# ---------------------------------------------------------------------------
# unit: the pure-Python policy functions
# ---------------------------------------------------------------------------

def test_effective_rbac_neither_modifier_inherits_project_default():
    plain = _Msg("plain")
    assert effective_rbac(plain, True) is True
    assert effective_rbac(plain, False) is False


def test_effective_rbac_protected_always_wins():
    protected = _Msg("p", is_protected=True)
    assert effective_rbac(protected, True) is True
    assert effective_rbac(protected, False) is True


def test_effective_rbac_open_always_wins_when_not_also_protected():
    open_msg = _Msg("o", is_open=True)
    assert effective_rbac(open_msg, True) is False
    assert effective_rbac(open_msg, False) is False


def test_transport_mode_matches_project_default_when_no_message_diverges():
    # covers: no messages, only plain messages, and the redundant cases
    # (`open` under an already-open default, `protected` under an already-
    # hardened default) -- none of these should ever ask for the new
    # kEmitTls/kClientCertRequired machinery.
    for hardening_required in (True, False):
        for msgs in ([], [_Msg("a")], [_Msg("a"), _Msg("b")],
                    [_Msg("a", is_open=not hardening_required)],
                    [_Msg("a", is_protected=hardening_required)]):
            emit_tls, client_cert_required = transport_mode(
                msgs, hardening_required)
            assert emit_tls == hardening_required
            assert client_cert_required == hardening_required


def test_transport_mode_open_message_under_hardened_default():
    msgs = [_Msg("a"), _Msg("b", is_open=True)]
    emit_tls, client_cert_required = transport_mode(msgs, True)
    assert emit_tls is True          # transport stays on
    assert client_cert_required is False  # but a cert is no longer mandatory


def test_transport_mode_protected_message_under_open_default():
    msgs = [_Msg("a"), _Msg("b", is_protected=True)]
    emit_tls, client_cert_required = transport_mode(msgs, False)
    assert emit_tls is True           # TLS gets promoted on for this project
    assert client_cert_required is False  # still optional -- most callers have none


def test_transport_mode_both_directions_at_once():
    msgs = [_Msg("a", is_open=True), _Msg("b", is_protected=True)]
    for hardening_required in (True, False):
        emit_tls, client_cert_required = transport_mode(
            msgs, hardening_required)
        assert emit_tls is True
        assert client_cert_required is False


# ---------------------------------------------------------------------------
# structural: REST bring-up
# ---------------------------------------------------------------------------

def test_rest_bringup_byte_identical_call_when_nothing_diverges(tmp_path):
    from Database.RestAdapter import RestAdapter
    dest = str(tmp_path)
    RestAdapter(messages=[_Msg("widget")], dest=dest, compliance=HARDENED,
                crypto_backend=get_backend("openssl_fips")).Process()
    bringup = _read(os.path.join(dest, "generated", "cpp", HTTP_OUT_SUBDIR,
                                 "http_server_bringup.h"))
    assert "inline constexpr bool kHardeningRequired = true;" in bringup
    assert "kEmitTls" not in bringup
    assert "kClientCertRequired" not in bringup
    assert "if (kHardeningRequired) {" in bringup
    assert "app_.ssl(make_server_context(kHardeningRequired, mtls));" in bringup


def test_rest_bringup_promotes_tls_for_protected_message_in_open_project(tmp_path):
    from Database.RestAdapter import RestAdapter
    dest = str(tmp_path)
    RestAdapter(messages=[_Msg("widget", is_protected=True)], dest=dest,
                compliance=OPEN_PROFILE,
                crypto_backend=get_backend("openssl")).Process()
    http_dir = os.path.join(dest, "generated", "cpp", HTTP_OUT_SUBDIR)
    bringup = _read(os.path.join(http_dir, "http_server_bringup.h"))
    assert "inline constexpr bool kHardeningRequired = false;" in bringup
    assert "inline constexpr bool kEmitTls = true;" in bringup
    assert "inline constexpr bool kClientCertRequired = false;" in bringup
    assert "if (kEmitTls) {" in bringup
    assert ("app_.ssl(make_server_context(kEmitTls, mtls, "
           "kClientCertRequired));") in bringup
    # the RBAC/session runtime must ship even though the project is
    # nominally unhardened -- this project's one message needs it.
    assert os.path.isfile(os.path.join(http_dir, RBAC_RUNTIME))
    assert os.path.isfile(os.path.join(http_dir, SESSION_RUNTIME))
    # and the message's own header must actually use the RBAC helper, not
    # the flat credential.
    rest_h = _read(os.path.join(dest, "generated", "cpp", "rest",
                               "widget_deadbeef_rest.h"))
    assert "authz_widget(" in rest_h
    assert "authorized_widget(" not in rest_h


def test_rest_bringup_relaxes_cert_for_open_message_in_hardened_project(tmp_path):
    from Database.RestAdapter import RestAdapter
    dest = str(tmp_path)
    RestAdapter(messages=[_Msg("gate", is_protected=False),
                          _Msg("lobby", is_open=True)],
               dest=dest, compliance=HARDENED,
               crypto_backend=get_backend("openssl_fips")).Process()
    http_dir = os.path.join(dest, "generated", "cpp", HTTP_OUT_SUBDIR)
    bringup = _read(os.path.join(http_dir, "http_server_bringup.h"))
    assert "inline constexpr bool kHardeningRequired = true;" in bringup
    assert "inline constexpr bool kEmitTls = true;" in bringup
    assert "inline constexpr bool kClientCertRequired = false;" in bringup
    # RBAC runtime still ships -- "gate" still needs it (inherits hardened).
    assert os.path.isfile(os.path.join(http_dir, RBAC_RUNTIME))
    gate_h = _read(os.path.join(dest, "generated", "cpp", "rest",
                               "gate_deadbeef_rest.h"))
    assert "authz_gate(" in gate_h
    lobby_h = _read(os.path.join(dest, "generated", "cpp", "rest",
                                "lobby_deadbeef_rest.h"))
    assert "authorized_lobby(" in lobby_h
    assert "authz_lobby(" not in lobby_h


def test_rest_bringup_stays_byte_identical_for_redundant_modifier_use(tmp_path):
    """`open` under an already-open project, or `protected` under an
    already-hardened one, is a documented no-op -- must not trip the mixed-
    mode machinery either."""
    from Database.RestAdapter import RestAdapter

    dest_a = str(tmp_path / "a")
    RestAdapter(messages=[_Msg("x", is_open=True)], dest=dest_a,
                compliance=OPEN_PROFILE,
                crypto_backend=get_backend("openssl")).Process()
    bringup_a = _read(os.path.join(dest_a, "generated", "cpp",
                                   HTTP_OUT_SUBDIR, "http_server_bringup.h"))
    assert "kEmitTls" not in bringup_a

    dest_b = str(tmp_path / "b")
    RestAdapter(messages=[_Msg("y", is_protected=True)], dest=dest_b,
                compliance=HARDENED,
                crypto_backend=get_backend("openssl_fips")).Process()
    bringup_b = _read(os.path.join(dest_b, "generated", "cpp",
                                   HTTP_OUT_SUBDIR, "http_server_bringup.h"))
    assert "kEmitTls" not in bringup_b


# ---------------------------------------------------------------------------
# structural: SOAP (no bring-up of its own -- just the per-message gate)
# ---------------------------------------------------------------------------

def test_soap_uses_per_message_gate(tmp_path):
    from Database.SoapAdapter import SoapAdapter
    dest = str(tmp_path)
    SoapAdapter(messages=[_Msg("gate"), _Msg("lobby", is_open=True)],
               dest=dest, compliance=HARDENED).Process()
    gate_h = _read(os.path.join(dest, "generated", "cpp", "soap",
                               "gate_deadbeef_soap.h"))
    lobby_h = _read(os.path.join(dest, "generated", "cpp", "soap",
                                "lobby_deadbeef_soap.h"))
    # RBAC variant renders no per-message authorized_<name> flat helper;
    # the flat variant does (see auth_gate.soap_auth_fills).
    assert "authorized_lobby(" in lobby_h
    assert "authorized_gate(" not in gate_h


# ---------------------------------------------------------------------------
# structural: gRPC bring-up
# ---------------------------------------------------------------------------

def test_grpc_bringup_byte_identical_call_when_nothing_diverges(tmp_path):
    from Database.GrpcServiceAdapter import GrpcServiceAdapter
    dest = str(tmp_path)
    GrpcServiceAdapter(messages=[_Msg("widget")], dest=dest,
                       compliance=HARDENED,
                       crypto_backend=get_backend("openssl_fips")).Process()
    bringup = _read(os.path.join(dest, "generated", "cpp", "grpc",
                                "grpc_server_bringup.h"))
    assert "kEmitTls" not in bringup
    assert ("server_credentials(kHardeningRequired, mtls));" in bringup)


def test_grpc_bringup_promotes_tls_for_protected_message_in_open_project(tmp_path):
    from Database.GrpcServiceAdapter import GrpcServiceAdapter
    dest = str(tmp_path)
    GrpcServiceAdapter(messages=[_Msg("widget", is_protected=True)],
                       dest=dest, compliance=OPEN_PROFILE,
                       crypto_backend=get_backend("openssl")).Process()
    grpc_dir = os.path.join(dest, "generated", "cpp", "grpc")
    bringup = _read(os.path.join(grpc_dir, "grpc_server_bringup.h"))
    assert "inline constexpr bool kHardeningRequired = false;" in bringup
    assert "inline constexpr bool kEmitTls = true;" in bringup
    assert "inline constexpr bool kClientCertRequired = false;" in bringup
    assert ("server_credentials(kEmitTls, mtls, kClientCertRequired));"
           in bringup)
    assert os.path.isfile(os.path.join(grpc_dir, RBAC_RUNTIME))
    widget_h = _read(os.path.join(grpc_dir, "widget_deadbeef_grpc.h"))
    assert "rbac_check(" in widget_h
    assert "authorized(::grpc::ServerContext" not in widget_h


def test_grpc_bringup_relaxes_cert_for_open_message_in_hardened_project(tmp_path):
    from Database.GrpcServiceAdapter import GrpcServiceAdapter
    dest = str(tmp_path)
    GrpcServiceAdapter(messages=[_Msg("gate"), _Msg("lobby", is_open=True)],
                       dest=dest, compliance=HARDENED,
                       crypto_backend=get_backend("openssl_fips")).Process()
    grpc_dir = os.path.join(dest, "generated", "cpp", "grpc")
    bringup = _read(os.path.join(grpc_dir, "grpc_server_bringup.h"))
    assert "inline constexpr bool kClientCertRequired = false;" in bringup
    lobby_h = _read(os.path.join(grpc_dir, "lobby_deadbeef_grpc.h"))
    assert "authorized(::grpc::ServerContext" in lobby_h
    assert "rbac_check(" not in lobby_h
    assert os.path.isfile(os.path.join(grpc_dir, GRPC_MTLS_RUNTIME))


def test_grpc_no_rbac_runtime_copied_when_no_message_needs_it(tmp_path):
    """An unhardened project with only plain/`open` messages (no `protected`
    anywhere) must not gain the RBAC runtime just because task 3 landed."""
    from Database.GrpcServiceAdapter import GrpcServiceAdapter
    dest = str(tmp_path)
    GrpcServiceAdapter(messages=[_Msg("a"), _Msg("b", is_open=True)],
                       dest=dest, compliance=OPEN_PROFILE,
                       crypto_backend=get_backend("openssl")).Process()
    grpc_dir = os.path.join(dest, "generated", "cpp", "grpc")
    assert not os.path.exists(os.path.join(grpc_dir, RBAC_RUNTIME))


# ---------------------------------------------------------------------------
# selection JSON is unaffected -- still records only the project-wide
# predicate, regardless of any per-message divergence (its documented
# purpose, per-message transport shape lives in the bring-up header itself)
# ---------------------------------------------------------------------------

def test_selection_json_unaffected_by_per_message_divergence(tmp_path):
    from Database.RestAdapter import RestAdapter
    dest = str(tmp_path)
    RestAdapter(messages=[_Msg("widget", is_protected=True)], dest=dest,
               compliance=OPEN_PROFILE,
               crypto_backend=get_backend("openssl")).Process()
    sel = json.loads(_read(os.path.join(
        dest, "generated", "cpp", HTTP_OUT_SUBDIR, "http_server_selection.json")))
    assert sel == {
        "hardening_required": False,
        "crypto_backend": "openssl",
        "cmake_package": "OpenSSL",
        "openssl_provider": "default",
        "fips": False,
    }
