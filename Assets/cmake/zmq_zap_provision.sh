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
#   zmq_zap_provision.sh <out_dir> [client_identity ...]
#
# Default: a single client identity "harpia-zmq-client" when none is named.
#
# Produces in <out_dir>:
#   zmq_server_secret.key        server CURVE secret key (z85, 40 chars)
#   zmq_server_public.key        server CURVE public key (z85)
#   zmq_<identity>_secret.key    per client identity: its CURVE secret key
#   zmq_<identity>_public.key    per client identity: its CURVE public key
#   allowlist.txt                one "<client_public_key> <identity>" per line --
#                                point HARPIA_ZMQ_ALLOWLIST at this
set -eu

if [ $# -lt 1 ]; then
    echo "usage: $0 <out_dir> [client_identity ...]" >&2
    exit 2
fi

OUT=$1
shift
[ $# -eq 0 ] && set -- harpia-zmq-client

CC=${CC:-cc}
command -v "$CC" >/dev/null 2>&1 || { echo "zmq_zap_provision: $CC not found" >&2; exit 3; }

mkdir -p "$OUT"
_keygen="$OUT/.keygen"
cat > "$_keygen.c" <<'EOF'
#include <stdio.h>
#include <zmq.h>
int main(void) {
    char pub[41], sec[41];
    if (zmq_curve_keypair(pub, sec) != 0) return 1;
    printf("%s %s\n", pub, sec);   /* public secret */
    return 0;
}
EOF
"$CC" "$_keygen.c" -o "$_keygen" -lzmq
rm -f "$_keygen.c"

# server keypair
set -- "$@"
_kp=$("$_keygen")
echo "${_kp% *}" > "$OUT/zmq_server_public.key"
echo "${_kp#* }" > "$OUT/zmq_server_secret.key"

: > "$OUT/allowlist.txt"
for _id in "$@"; do
    _kp=$("$_keygen")
    _pub=${_kp% *}
    _sec=${_kp#* }
    echo "$_pub" > "$OUT/zmq_${_id}_public.key"
    echo "$_sec" > "$OUT/zmq_${_id}_secret.key"
    echo "$_pub $_id" >> "$OUT/allowlist.txt"
done
rm -f "$_keygen"

echo "zmq_zap_provision: server keypair + client identities [$*] + allowlist.txt in $OUT"
