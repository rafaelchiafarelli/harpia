"""CryptoBackend registry -- the compile-time seam choosing which underlying
crypto module a generated project links against (Foundation F5).

Mirrors Database/backends/ (base.py's ABC + __init__.py's registry/
get_backend) exactly, one level up in abstraction: DbBackend answers "which
SQL dialect", CryptoBackend answers "which crypto module" (e.g. standard vs.
FIPS-validated OpenSSL). Both Track O (key-wrap/envelope-encryption) and
Track C (TLS stack) must resolve their crypto module through this single
seam, not each pick their own -- see
Initiatives/medical_devices/harpia_medical_master_plan.md's F5 entry and
Initiatives/medical_devices/epics/thread-0-foundation/histories/
CryptoBackend-selection-point-done.md.

Foundation's scope stops at the seam itself: no real cryptographic
operations are implemented anywhere in this repo yet (Track O/C haven't
started), so neither concrete backend below does anything beyond describing
which module a build would link against and how. That's deliberate --
"doesn't ship or validate the crypto modules themselves — just the seam."
"""
import os
from abc import ABC, abstractmethod

from Compliance.context import RiskClass, Topology


class CryptoBackend(ABC):
    #: harpia backend id, as used by the HARPIA_CRYPTO_BACKEND env var.
    name: str = ""
    #: whether this backend is FIPS 140-validated.
    fips: bool = False

    @property
    @abstractmethod
    def cmake_package(self) -> str:
        """CMake `find_package()` name a generated build's CMakeLists
        should request for this backend (e.g. "OpenSSL"). Both Track O and
        Track C consume this same value, so they provably link the same
        module within one build."""

    @property
    @abstractmethod
    def openssl_provider(self) -> str:
        """OpenSSL 3.x provider name to load (e.g. "default" or "fips") --
        the actual FIPS-module swap, once Track O/C wire real TLS/envelope-
        encryption code against this seam."""

    def sbom_entry(self) -> dict:
        """Build metadata for Track M's future SBOM emission: which crypto
        module this project actually links against. Track M doesn't exist
        yet -- this is the record it will read once it does."""
        return {"crypto_backend": self.name, "fips_validated": self.fips,
                "cmake_package": self.cmake_package,
                "openssl_provider": self.openssl_provider}

    def __repr__(self):
        return "<CryptoBackend {!r} (fips={})>".format(self.name, self.fips)


class StandardOpenSSLBackend(CryptoBackend):
    name = "openssl"
    fips = False

    @property
    def cmake_package(self):
        return "OpenSSL"

    @property
    def openssl_provider(self):
        return "default"


class FipsOpenSSLBackend(CryptoBackend):
    name = "openssl_fips"
    fips = True

    @property
    def cmake_package(self):
        return "OpenSSL"

    @property
    def openssl_provider(self):
        return "fips"


DEFAULT_BACKEND = "openssl"

# name -> singleton (backends are stateless, same as Database/backends).
_REGISTRY = {b.name: b for b in (StandardOpenSSLBackend(), FipsOpenSSLBackend())}
_ALIASES = {"standard": "openssl", "fips": "openssl_fips"}


def get_backend(name=None, compliance=None):
    """Return the :class:`CryptoBackend` for `name` (or a compliance-driven /
    hardcoded default). Raises `ValueError` on an unknown name, so a bad
    HARPIA_CRYPTO_BACKEND value fails loudly at generation time -- same
    convention as Database.backends.get_backend.

    Selection order:
      1. an explicit `name` wins outright (e.g. HARPIA_CRYPTO_BACKEND).
      2. otherwise, if `compliance` is given, its risk_class/topology decide
         the default -- CLASS_C or CLOUD_CONNECTED implies the FIPS-
         validated backend, matching the project-wide-floor rule (§0a): one
         hardening floor per project, never a per-jurisdiction fan-out.
      3. otherwise DEFAULT_BACKEND ("openssl").
    """
    if name is None and compliance is not None:
        if (compliance.risk_class == RiskClass.CLASS_C
                or compliance.topology == Topology.CLOUD_CONNECTED):
            name = "openssl_fips"

    key = (name or DEFAULT_BACKEND).strip().lower()
    key = _ALIASES.get(key, key)
    try:
        return _REGISTRY[key]
    except KeyError:
        raise ValueError("unknown harpia crypto backend {!r}; known: {}".format(
            name, ", ".join(sorted(_REGISTRY))))


def register(backend):
    """Register an additional backend (e.g. a real HSM-backed one, later)."""
    if not isinstance(backend, CryptoBackend):
        raise TypeError("backend must be a CryptoBackend, got {!r}".format(backend))
    _REGISTRY[backend.name] = backend


def write_build_metadata(backend, dest):
    """Persist the selected backend's sbom_entry() under
    <dest>/build_metadata/crypto_backend.json -- the "recorded as build
    metadata for Track M's SBOM" guarantee. Track M doesn't exist yet, so
    nothing reads this back today; it exists so that track doesn't have to
    re-derive the choice, only read a file already there."""
    import json
    from Util.util import write_if_different

    metadata_dir = os.path.join(dest, "build_metadata")
    os.makedirs(metadata_dir, exist_ok=True)
    path = os.path.join(metadata_dir, "crypto_backend.json")
    write_if_different(path, json.dumps(backend.sbom_entry(), indent=2) + "\n")
    return path


__all__ = ["CryptoBackend", "StandardOpenSSLBackend", "FipsOpenSSLBackend",
           "get_backend", "register", "write_build_metadata",
           "DEFAULT_BACKEND"]
