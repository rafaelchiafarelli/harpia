"""Tests for Foundation F5 -- the CryptoBackend selection point.

Per initiatives/medical_devices/epics/thread-0-foundation/histories/
CryptoBackend-selection-point-done.md:
  - Unit: build-flag selection actually changes which module gets linked.
  - Integration/acceptance gate: Track O and Track C would provably agree
    on which crypto module is linked within the same build -- neither
    track exists in this repo yet, so this is checked at the seam itself
    (get_backend() returns the identical singleton every call, exactly
    like Database.backends.get_backend) plus the build-metadata sidecar
    F5's own guarantee calls for.
"""
import json
import os

import pytest

from Compliance.context import ComplianceContext, PhiHandling, RiskClass, Topology
from Crypto.backend import (
    FipsOpenSSLBackend,
    StandardOpenSSLBackend,
    get_backend,
    write_build_metadata,
)


def _ctx(risk_class=RiskClass.CLASS_A, topology=Topology.STANDALONE):
    return ComplianceContext(risk_class=risk_class, topology=topology,
                             phi_handling=PhiHandling.NONE, jurisdiction=[])


# -- unit: selection actually changes which module is returned --------------

def test_default_backend_is_standard_openssl():
    b = get_backend()
    assert isinstance(b, StandardOpenSSLBackend)
    assert b.name == "openssl"
    assert b.fips is False


def test_explicit_name_selects_fips_backend():
    b = get_backend("openssl_fips")
    assert isinstance(b, FipsOpenSSLBackend)
    assert b.fips is True


def test_alias_resolves_to_canonical_name():
    assert get_backend("standard").name == "openssl"
    assert get_backend("fips").name == "openssl_fips"


def test_unknown_backend_name_is_a_hard_error():
    with pytest.raises(ValueError):
        get_backend("rot13")


def test_explicit_name_wins_over_compliance():
    # risk_class=CLASS_C alone would imply FIPS -- an explicit name overrides it.
    b = get_backend("openssl", compliance=_ctx(risk_class=RiskClass.CLASS_C))
    assert b.name == "openssl"


def test_class_c_risk_class_defaults_to_fips():
    b = get_backend(compliance=_ctx(risk_class=RiskClass.CLASS_C,
                                    topology=Topology.STANDALONE))
    assert b.fips is True


def test_cloud_connected_topology_defaults_to_fips():
    b = get_backend(compliance=_ctx(risk_class=RiskClass.CLASS_A,
                                    topology=Topology.CLOUD_CONNECTED))
    assert b.fips is True


def test_low_risk_standalone_defaults_to_standard():
    b = get_backend(compliance=_ctx(risk_class=RiskClass.CLASS_A,
                                    topology=Topology.STANDALONE))
    assert b.fips is False


# -- acceptance gate: one project, one crypto module, provably shared ------

def test_backend_is_a_stable_singleton():
    # Track O and Track C, once built, resolve through this same call --
    # proving they'd link the identical module within one build reduces to
    # this object identity holding across independent calls.
    assert get_backend() is get_backend()
    assert get_backend("openssl_fips") is get_backend("openssl_fips")


# -- build metadata (F5's "recorded for Track M's SBOM" guarantee) ---------

def test_write_build_metadata_produces_valid_sidecar(tmp_path):
    backend = get_backend("openssl_fips")
    path = write_build_metadata(backend, str(tmp_path))
    assert os.path.isfile(path)
    with open(path) as f:
        data = json.load(f)
    assert data == {
        "crypto_backend": "openssl_fips",
        "fips_validated": True,
        "cmake_package": "OpenSSL",
        "openssl_provider": "fips",
    }


def test_write_build_metadata_is_write_if_different(tmp_path):
    backend = get_backend()
    path = write_build_metadata(backend, str(tmp_path))
    mtime1 = os.stat(path).st_mtime_ns
    write_build_metadata(backend, str(tmp_path))
    mtime2 = os.stat(path).st_mtime_ns
    assert mtime1 == mtime2
