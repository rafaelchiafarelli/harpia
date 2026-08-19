#!/usr/bin/env bash
#
# setup-env.sh — one-shot environment setup for a freshly cloned harpia repo.
#
# Sets up the host-only Python path (venv + pytest, per tests/README.md) and
# checks whether the full Docker toolchain (protoc/gRPC/cmake/g++/ZMQ) is
# available. The Docker path is required for anything beyond the pure-Python
# golden-file tests (compiling generated C++, running the demo, etc.) but is
# not required for this script to succeed.
#
#   ./setup-env.sh
#
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$REPO_ROOT"

ok()   { echo "  [ok] $*"; }
warn() { echo "  [!!] $*"; }
info() { echo "$*"; }

info "=== harpia environment setup ==="
info "repo: $REPO_ROOT"
echo

# --- Python -----------------------------------------------------------------
info "-- Python --"
if ! command -v python3 >/dev/null 2>&1; then
    warn "python3 not found on PATH; install it and re-run."
    exit 1
fi
ok "$(python3 --version)"

if ! python3 -c 'import ensurepip' >/dev/null 2>&1; then
    warn "python3-venv (ensurepip) missing; installing via apt (needs sudo)..."
    PYVER="$(python3 -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')"
    sudo apt-get update
    sudo apt-get install -y "python${PYVER}-venv" || sudo apt-get install -y python3-venv
fi
ok "venv module available"

# --- venv + pytest ------------------------------------------------------------
info "-- Python venv + pytest --"
if [ ! -x .venv/bin/python ]; then
    python3 -m venv .venv
    ok "created .venv"
else
    ok ".venv already exists"
fi
.venv/bin/pip install --quiet --upgrade pip pytest pyyaml
ok "pytest installed: $(.venv/bin/python -m pytest --version 2>&1 | head -1)"
ok "pyyaml installed (needed by GuiAdapter/tool/generator.py)"

# --- case-sensitivity sanity check --------------------------------------------
# On a case-insensitive filesystem (macOS, or a Windows-mounted /mnt/c path in
# WSL), `import Logger.logger` and `import logger.logger` both resolve, so a
# module-casing mismatch stays invisible there. This repo has been bitten by
# that before (Logger/Message/ProtoFile/Util were renamed lowercase but not
# every `from X.y import` was updated) and it only surfaces as a hard failure
# on a genuinely case-sensitive filesystem like this one. Catch it here rather
# than at generator runtime.
info "-- case-sensitivity check (main.py import chain) --"
if .venv/bin/python -c "import sys; sys.path.insert(0, '.'); import main" 2>/tmp/harpia-import-check.log; then
    ok "main.py imports cleanly"
else
    warn "main.py failed to import — likely a module-casing mismatch:"
    sed 's/^/      /' /tmp/harpia-import-check.log
fi
rm -f /tmp/harpia-import-check.log

# --- Docker toolchain (optional but recommended) -----------------------------
info "-- Docker toolchain (protoc/gRPC/cmake/g++/ZMQ) --"
DOCKER_OK=0
if command -v docker >/dev/null 2>&1 && docker info >/dev/null 2>&1; then
    ok "docker is available and the daemon is reachable"
    DOCKER_OK=1
else
    warn "docker is not usable from this shell."
    warn "On WSL2 with Docker Desktop: open Docker Desktop on Windows, then"
    warn "Settings > Resources > WSL Integration, and enable it for this distro"
    warn "(\"$(cat /etc/os-release 2>/dev/null | grep -oP '(?<=^NAME=\")[^\"]+' || echo this distro)\" / \$WSL_DISTRO_NAME=${WSL_DISTRO_NAME:-unknown})."
    warn "Full-toolchain runs (docker/run.sh, run_harpia.sh) need this; the"
    warn "pure-Python test suite below works without it."
fi

# --- git / SSH remote ---------------------------------------------------------
info "-- git remote --"
if git remote get-url origin >/dev/null 2>&1; then
    ok "origin: $(git remote get-url origin)"
    if git ls-remote --exit-code origin >/dev/null 2>&1; then
        ok "origin is reachable"
    else
        warn "origin is configured but not reachable (check SSH key / network)"
    fi
fi

# --- self-check: run the pure-Python test suite -------------------------------
info "-- running pure-Python test suite (compile/toolchain tests auto-skip) --"
if .venv/bin/python -m pytest -q; then
    ok "test suite passed"
else
    warn "test suite reported failures; see output above"
fi

echo
info "=== done ==="
info "Next steps:"
info "  source .venv/bin/activate && python -m pytest      # host-only, Python tests"
info "  python3 main.py                                    # run the generator (stage 0-6 need no toolchain)"
if [ "$DOCKER_OK" -eq 1 ]; then
    info "  docker/run.sh pytest                               # full suite incl. C++ compile/run"
    info "  ./run_harpia.sh <input_folder> <output_folder>     # generate + build + ctest"
else
    info "  (enable Docker Desktop WSL integration to unlock docker/run.sh and run_harpia.sh)"
fi
