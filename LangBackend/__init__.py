"""Language-backend registry: which target(s) ``main.py`` generates.

Select a target with :func:`get_lang_backend` (default ``"cpp"``). ``main.py``
resolves ``HARPIA_GEN_LANG`` once and calls the resulting backend's
:meth:`~LangBackend.base.LangBackend.run` with a
:class:`~LangBackend.base.GenerationContext`. Same shape as
``Database.backends.get_backend``: explicit name, alias resolution, and an
unknown name is a hard error. A new language registers itself here (one
module + one entry in ``_REGISTRY``) without touching the existing backends.
"""
from LangBackend.base import GenerationContext, LangBackend
from LangBackend.cpp import CppBackend

DEFAULT_LANG = "cpp"

# name -> singleton (backends are stateless).
_REGISTRY = {b.name: b for b in (CppBackend(),)}
# convenience aliases for HARPIA_GEN_LANG
_ALIASES = {"c++": "cpp", "cxx": "cpp"}


def get_lang_backend(name=None):
    """Return the :class:`LangBackend` for ``name`` (or the default). An empty
    or missing name means the default. Raises ``ValueError`` on an unknown
    name so a typo in ``HARPIA_GEN_LANG`` fails loudly at generation time."""
    key = (name or DEFAULT_LANG).strip().lower() or DEFAULT_LANG
    key = _ALIASES.get(key, key)
    try:
        return _REGISTRY[key]
    except KeyError:
        raise ValueError("unknown harpia generation language {!r}; known: {}".format(
            name, ", ".join(sorted(_REGISTRY))))


def register(backend):
    """Register an additional language backend."""
    if not isinstance(backend, LangBackend):
        raise TypeError("backend must be a LangBackend, got {!r}".format(backend))
    _REGISTRY[backend.name] = backend


__all__ = ["LangBackend", "GenerationContext", "CppBackend",
           "get_lang_backend", "register", "DEFAULT_LANG"]
