"""OMG DDS-Security for the Python DDS transport: a fail-safe secured
participant (the Python side of ``DdsAdapter/runtime/harpia_dds_security.h``).

Hand-written, copied into a generated project as
``harpia_runtime.dds.security``. Security is configured the Cyclone-native
way, exactly as C++ does: a ``<CycloneDDS><Domain id="any"><Security>``
configuration document (:func:`security_config_xml`, byte-identical to the
C++ one) naming the builtin authentication / access-control / cryptographic
plugins and the six PKI files. cyclonedds-python takes it as the ``config``
of an explicitly created :class:`~cyclonedds.domain.Domain`; every
participant later created on that domain id in this process is secured.

Fail-safe: incomplete :class:`SecurityFiles` raise :class:`SecurityRefused`,
and so does a domain id that already exists in this process (its
configuration -- possibly plaintext -- is fixed; Cyclone would otherwise
silently reuse it). **Never a silent plaintext participant.**

The governance and permissions documents are the language-neutral ones
``DdsAdapter`` emits; the Python project carries a copy in
``harpia_generated/dds/security/`` (``governance.xml``, ``permissions.xml``,
``dds_security_selection.json``). Sign them for a deployment with
``Assets/cmake/dds_security_provision.sh`` (which also fills the
permissions subject), the same step as for C++.

``openssl_provider`` is the F5 CryptoBackend's choice; Cyclone's plugins take
their OpenSSL provider from the process OpenSSL configuration, so it is only
recorded in the configuration comment (as in C++).
"""
import threading
from dataclasses import dataclass
from xml.sax.saxutils import escape

from cyclonedds.core import DDSException
from cyclonedds.domain import Domain, DomainParticipant

_LOCK = threading.Lock()
#: secured domains created by this process (kept alive for its lifetime)
_DOMAINS: dict[int, Domain] = {}


@dataclass(frozen=True)
class SecurityFiles:
    """The six PKI artifacts of a DDS-Security participant (file paths;
    Cyclone reads them itself)."""

    identity_ca: str = ""
    identity_certificate: str = ""
    private_key: str = ""
    permissions_ca: str = ""
    #: the S/MIME-signed governance document
    governance: str = ""
    #: the S/MIME-signed permissions document
    permissions: str = ""

    def complete(self) -> bool:
        """True when every path is set."""
        return all((self.identity_ca, self.identity_certificate, self.private_key,
                    self.permissions_ca, self.governance, self.permissions))


class SecurityRefused(RuntimeError):
    """Raised instead of ever building a plaintext participant."""

    def __init__(self, what: str) -> None:
        super().__init__("DDS-Security refused: " + what)


def _x(text: str) -> str:
    return escape(text, {'"': "&quot;"})


def security_config_xml(files: SecurityFiles, openssl_provider: str = "default") -> str:
    """The Cyclone configuration document (the C++
    ``detail::security_config_xml``, byte for byte)."""
    return (
        '<CycloneDDS><Domain id="any">'
        "<!-- harpia DDS-Security; crypto module via F5 CryptoBackend, "
        "openssl_provider=" + _x(openssl_provider) + " -->"
        "<Security>"
        "<Authentication>"
        '<Library path="dds_security_auth" '
        'initFunction="init_authentication" '
        'finalizeFunction="finalize_authentication"/>'
        "<IdentityCA>file:" + _x(files.identity_ca) + "</IdentityCA>"
        "<IdentityCertificate>file:" + _x(files.identity_certificate)
        + "</IdentityCertificate>"
        "<PrivateKey>file:" + _x(files.private_key) + "</PrivateKey>"
        "</Authentication>"
        "<AccessControl>"
        '<Library path="dds_security_ac" '
        'initFunction="init_access_control" '
        'finalizeFunction="finalize_access_control"/>'
        "<PermissionsCA>file:" + _x(files.permissions_ca) + "</PermissionsCA>"
        "<Governance>file:" + _x(files.governance) + "</Governance>"
        "<Permissions>file:" + _x(files.permissions) + "</Permissions>"
        "</AccessControl>"
        "<Cryptographic>"
        '<Library path="dds_security_crypto" '
        'initFunction="init_crypto" '
        'finalizeFunction="finalize_crypto"/>'
        "</Cryptographic>"
        "</Security>"
        "</Domain></CycloneDDS>")


def secured_participant(domain_id: int, files: SecurityFiles,
                        openssl_provider: str = "default") -> DomainParticipant:
    """A DomainParticipant on a secured ``domain_id``. The first call per
    domain id creates the domain with the security configuration; a domain
    that already exists unsecured (a plain participant was made on it first)
    is refused."""
    if not files.complete():
        raise SecurityRefused(
            "incomplete SecurityFiles (need identity CA + certificate + private key, "
            "and permissions CA + governance + permissions)")
    with _LOCK:
        if domain_id not in _DOMAINS:
            xml = security_config_xml(files, openssl_provider)
            try:
                _DOMAINS[domain_id] = Domain(domain_id, xml)
            except (DDSException, UnicodeEncodeError) as e:
                raise SecurityRefused(
                    f"cannot create secured domain {domain_id} (it may already exist "
                    f"unsecured in this process): {e}") from None
        return DomainParticipant(domain_id)
