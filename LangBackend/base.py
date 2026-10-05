"""The :class:`LangBackend` interface and the :class:`GenerationContext` every
backend receives.

A language backend owns everything ``main.py`` does *after* the
language-neutral front end (pre-lex, lex, message creation, ``.proto``
emission, the framework protos and the DB-dialect / crypto-module
selection). ``main.py`` builds one :class:`GenerationContext` and hands it to
exactly one backend's :meth:`LangBackend.run`.

The shared selections (``db_backend``, ``crypto_backend``) are resolved once
in ``main.py`` and carried here, never re-resolved inside a backend, so every
target in one run sees the identical object (``JavaDatabase/CLAUDE.md``).
"""
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, List


@dataclass(frozen=True)
class GenerationContext:
    """Everything a backend needs from the front end, resolved once per run."""
    messages: List[Any]
    dest: str
    compliance: Any
    db_backend: Any
    crypto_backend: Any
    root_hash: str
    log: Any

    def report(self, error):
        """Log a stage's non-fatal ``Error`` (``None`` means the stage succeeded)."""
        if error is not None:
            self.log.print(error.__str__())


class LangBackend(ABC):
    """One generation target. Stateless, so the registry keeps a singleton."""

    #: registry key, as given to ``HARPIA_GEN_LANG``
    name = None

    @abstractmethod
    def run(self, ctx):
        """Run every generation stage of this target into ``ctx.dest``."""

    def __repr__(self):
        return "<LangBackend {}>".format(self.name)
