"""The LangBackend registry (python-target / lang-backend-seam).

Same contract as Database.backends.get_backend: default when unset, alias
resolution, case/whitespace-insensitive, a hard error on an unknown name,
and one singleton per backend. Pure Python.
"""
import pytest

from LangBackend import (CppBackend, DEFAULT_LANG, GenerationContext,
                         LangBackend, get_lang_backend, register)


def test_default_is_cpp():
    assert DEFAULT_LANG == "cpp"
    for name in (None, "", "  "):
        assert isinstance(get_lang_backend(name), CppBackend)


def test_cpp_resolves_by_name_and_alias():
    b = get_lang_backend("cpp")
    assert isinstance(b, CppBackend) and b.name == "cpp"
    assert get_lang_backend(" CPP ") is b
    assert get_lang_backend("c++") is b


def test_same_singleton_every_call():
    assert get_lang_backend() is get_lang_backend("cpp")


def test_unknown_name_is_a_hard_error():
    with pytest.raises(ValueError, match="unknown harpia generation language"):
        get_lang_backend("cobol")


def test_register_rejects_non_backend():
    with pytest.raises(TypeError):
        register(object())


def test_register_adds_a_new_language():
    class _Probe(LangBackend):
        name = "probe-lang"

        def run(self, ctx):
            ctx.log.print("ran")

    probe = _Probe()
    register(probe)
    try:
        assert get_lang_backend("probe-lang") is probe
    finally:
        from LangBackend import _REGISTRY
        _REGISTRY.pop("probe-lang", None)


def test_context_report_logs_only_errors():
    lines = []

    class _Log:
        def print(self, s):
            lines.append(s)

    ctx = GenerationContext(messages=[], dest="x", compliance=None,
                            db_backend=None, crypto_backend=None,
                            root_hash="h", log=_Log())
    ctx.report(None)
    ctx.report("boom")
    assert lines == ["boom"]


def test_java_is_additive_on_cpp():
    from LangBackend import JavaBackend
    b = get_lang_backend("java")
    assert isinstance(b, JavaBackend) and b.name == "java"
    assert isinstance(b, CppBackend)
    assert get_lang_backend("JAVA") is b
