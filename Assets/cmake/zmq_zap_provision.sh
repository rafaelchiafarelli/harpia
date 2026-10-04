#!/bin/sh
# Configure-time helper for the ZMQ CURVE ZAP allowlist (transport-authn epic,
# "zmq-zap-allowlist") -- the ZMQ analogue of Assets/cmake/mtls_provision.sh.
# Mints CURVE keypairs (a server keypair plus one or more client identities) and
# writes the HARPIA_ZMQ_ALLOWLIST file the generated ZAP handler reads at
# startup, so the demo and the integration tests have real keys to allow / deny.
#
#   NOT a production identity store. A real deployment provisions client public
#   keys from its own key store; rotation/revocation is "edit the file and
#   restart". This exists so "unknown key -> handshake refused, allowlisted key
#   -> accepted" can be proven end to end.
#
# Usage:
#   zmq_zap_provision.sh <out_dir> [client_identity ...] [--clients-file <path>]
#
# Default: a single client identity "harpia-zmq-client" when none is named.
#
# --clients-file <path> (multi-system-reference / reference-system task 1,
# additive): the same "<identity> <role>" file mtls_provision.sh reads (the role
# column is ignored here -- ZAP admits or refuses a key, it has no roles), so
# one identity list provisions both the mTLS certificates and the CURVE keys.
# Identities are [A-Za-z0-9._-] only.
#
# Re-runs are idempotent: an existing server keypair and existing per-identity
# keypairs are kept, not re-keyed. allowlist.txt is rewritten to list exactly
# the identities named in this run.
#
# Produces in <out_dir>:
#   zmq_server_secret.key        server CURVE secret key (z85, 40 chars)
#   zmq_server_public.key        server CURVE public key (z85)
#   zmq_<identity>_secret.key    per client identity: its CURVE secret key
#   zmq_<identity>_public.key    per client identity: its CURVE public key
#   allowlist.txt                one "<client_public_key> <identity>" per line --
#                                point HARPIA_ZMQ_ALLOWLIST at this
set -eu

usage() {
    echo "usage: $0 <out_dir> [client_identity ...] [--clients-file <path>]" >&2
    exit 2
}

if [ $# -lt 1 ]; then
    usage
fi

OUT=$1
shift

CLIENTS_FILE=""
IDS=""
while [ $# -gt 0 ]; do
    case "$1" in
        --clients-file)
            [ $# -ge 2 ] || usage
            CLIENTS_FILE=$2; shift 2 ;;
        --*) echo "zmq_zap_provision: unknown option $1" >&2; usage ;;
        *)  IDS="$IDS
$1"; shift ;;
    esac
done

valid_id() {
    case "$1" in
        ''|*[!A-Za-z0-9._-]*) return 1 ;;
        *) return 0 ;;
    esac
}

if [ -n "$CLIENTS_FILE" ]; then
    [ -r "$CLIENTS_FILE" ] || { echo "zmq_zap_provision: cannot read $CLIENTS_FILE" >&2; exit 2; }
    _n=0
    while IFS= read -r _line || [ -n "$_line" ]; do
        _n=$((_n + 1))
        _line=$(printf '%s' "$_line" | tr -d '\r')
        case "$_line" in ''|'#'*) continue ;; esac
        # shellcheck disable=SC2086
        set -- $_line
        if [ $# -lt 1 ] || ! valid_id "$1"; then
            echo "zmq_zap_provision: $CLIENTS_FILE:$_n: expected '<identity> [role]' with identity in [A-Za-z0-9._-]" >&2
            exit 2
        fi
        IDS="$IDS
$1"
    done < "$CLIENTS_FILE"
fi
IDS=$(printf '%s\n' "$IDS" | sed '/^$/d' | awk '!seen[$0]++')
[ -n "$IDS" ] || IDS=harpia-zmq-client
for _id in $IDS; do
    valid_id "$_id" || { echo "zmq_zap_provision: invalid identity '$_id'" >&2; exit 2; }
done

CC=${CC:-cc}
command -v "$CC" >/dev/null 2>&1 || { echo "zmq_zap_provision: $CC not found" >&2; exit 3; }

mkdir -p "$OUT"
_keygen="$OUT/.keygen"
# one keygen run mints N keypairs (one line each): spawning a process per key
# is fine for a handful, slow for thousands
cat > "$_keygen.c" <<'EOF'
#include <stdio.h>
#include <stdlib.h>
#include <zmq.h>
int main(int argc, char** argv) {
    int n = argc > 1 ? atoi(argv[1]) : 1;
    for (int i = 0; i < n; ++i) {
        char pub[41], sec[41];
        if (zmq_curve_keypair(pub, sec) != 0) return 1;
        printf("%s %s\n", pub, sec);   /* public secret */
    }
    return 0;
}
EOF
"$CC" "$_keygen.c" -o "$_keygen" -lzmq
rm -f "$_keygen.c"

# server keypair (kept when present)
if ! [ -s "$OUT/zmq_server_public.key" ] || ! [ -s "$OUT/zmq_server_secret.key" ]; then
    _kp=$("$_keygen" 1)
    echo "${_kp% *}" > "$OUT/zmq_server_public.key"
    echo "${_kp#* }" > "$OUT/zmq_server_secret.key"
fi

# which identities still need a keypair
_need=""
_n_need=0
for _id in $IDS; do
    if ! [ -s "$OUT/zmq_${_id}_public.key" ] || ! [ -s "$OUT/zmq_${_id}_secret.key" ]; then
        _need="$_need $_id"
        _n_need=$((_n_need + 1))
    fi
done
if [ "$_n_need" -gt 0 ]; then
    "$_keygen" "$_n_need" > "$OUT/.keys"
    _i=0
    for _id in $_need; do
        _i=$((_i + 1))
        _kp=$(sed -n "${_i}p" "$OUT/.keys")
        echo "${_kp% *}" > "$OUT/zmq_${_id}_public.key"
        echo "${_kp#* }" > "$OUT/zmq_${_id}_secret.key"
    done
    rm -f "$OUT/.keys"
fi
rm -f "$_keygen"

: > "$OUT/allowlist.txt.tmp"
for _id in $IDS; do
    echo "$(cat "$OUT/zmq_${_id}_public.key") $_id" >> "$OUT/allowlist.txt.tmp"
done
mv "$OUT/allowlist.txt.tmp" "$OUT/allowlist.txt"

_count=$(printf '%s\n' "$IDS" | wc -l | tr -d ' ')
echo "zmq_zap_provision: server keypair + $_count client identit(y/ies) ($_n_need new) + allowlist.txt in $OUT"
