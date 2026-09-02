#!/bin/sh
# Configure-time helper for -DUSE_MTLS=ON (transport-authn epic, task 1) --
# the mTLS analogue of Assets/cmake/dds_security_provision.sh. Mints a local
# CA and issues a server certificate plus one or more client certificates so
# a generated project's gRPC / REST / SOAP endpoints can require *and verify*
# a client certificate without hand-managed PKI.
#
#   NOT a production identity store. A real deployment provisions identities
#   from its own CA / HSM. The identity -> role binding these client-cert
#   subjects feed into is transport-authn task 4 (RBAC). This script exists so
#   the demo and the integration tests can prove "no client cert -> refused,
#   valid client cert -> allowed" end to end, and so task 4 has real
#   per-identity certificates to map onto roles.
#
# Key strength follows the F5 CryptoBackend seam's selected module: pass the
# OpenSSL provider in the HARPIA_MTLS_PROVIDER env var -- the value of
# CryptoBackend.transport_security()["openssl_provider"], "default" or "fips".
# "fips" -> RSA-3072 / SHA-384; anything else -> RSA-2048 / SHA-256 (the same
# rsa:2048 baseline dds_security_provision.sh uses).
#
# Usage:
#   mtls_provision.sh <out_dir> [server_CN] [client_identity ...]
#
# Defaults: server_CN = "localhost"; a single client identity "harpia-client"
# when none is named.
#
# Produces in <out_dir>:
#   ca.pem                      local CA cert -- trust anchor for BOTH the
#                               server (client verifying the server) and the
#                               clients (server verifying the client)
#   ca_key.pem                  its private key (used only to sign, here)
#   server.pem                  server identity cert: EKU serverAuth,
#                               SAN = <server_CN>, localhost, 127.0.0.1
#   server_key.pem              its private key
#   client.pem                  first client identity cert: EKU clientAuth,
#                               subject CN = the identity name (this is the
#                               string task 4 maps to a role)
#   client_key.pem              its private key
#   client_<identity>.pem       additional client identities past the first,
#   client_<identity>_key.pem   one cert/key pair each
set -eu

if [ $# -lt 1 ]; then
    echo "usage: $0 <out_dir> [server_CN] [client_identity ...]" >&2
    exit 2
fi

OUT=$1
shift
SERVER_CN=${1:-localhost}
if [ $# -gt 0 ]; then shift; fi
# whatever is left in "$@" is the explicit client-identity list
if [ $# -eq 0 ]; then
    set -- harpia-client
fi

command -v openssl >/dev/null 2>&1 || { echo "mtls_provision: openssl not found" >&2; exit 3; }

case "${HARPIA_MTLS_PROVIDER:-default}" in
    fips) BITS=3072; SIG=sha384 ;;
    *)    BITS=2048; SIG=sha256 ;;
esac

mkdir -p "$OUT"

# 1. local CA -- the single trust anchor for both directions of the handshake.
openssl req -x509 -nodes -newkey "rsa:$BITS" "-$SIG" -days 3650 \
    -keyout "$OUT/ca_key.pem" -out "$OUT/ca.pem" \
    -subj "/O=harpia/CN=harpia-local-mtls-ca" >/dev/null 2>&1

# issue <basename> <subject> <extfile-contents>
#   signs a fresh key + CSR with the CA and the given x509 extensions.
issue() {
    _base=$1
    _subj=$2
    _ext=$3
    _extf="$OUT/$_base.ext"
    printf '%s\n' "$_ext" > "$_extf"
    openssl req -nodes -newkey "rsa:$BITS" "-$SIG" \
        -keyout "$OUT/${_base}_key.pem" -out "$OUT/$_base.csr" \
        -subj "$_subj" >/dev/null 2>&1
    openssl x509 -req -in "$OUT/$_base.csr" -days 3650 "-$SIG" \
        -CA "$OUT/ca.pem" -CAkey "$OUT/ca_key.pem" -CAcreateserial \
        -extfile "$_extf" -out "$OUT/$_base.pem" >/dev/null 2>&1
    rm -f "$OUT/$_base.csr" "$_extf" "$OUT/ca.srl"
}

# 2. server identity -- serverAuth + SAN (modern TLS stacks reject a bare CN).
issue server "/O=harpia/CN=$SERVER_CN" \
"basicConstraints=CA:FALSE
keyUsage=digitalSignature,keyEncipherment
extendedKeyUsage=serverAuth
subjectAltName=DNS:$SERVER_CN,DNS:localhost,IP:127.0.0.1"

# 3. one client identity per name. The first is also written as the
#    unqualified client.pem / client_key.pem the generated demo client and the
#    task-2/3 integration tests pick up without needing to know the identity
#    name.
_first=1
for _id in "$@"; do
    issue "client_$_id" "/O=harpia/CN=$_id" \
"basicConstraints=CA:FALSE
keyUsage=digitalSignature,keyEncipherment
extendedKeyUsage=clientAuth"
    if [ "$_first" = 1 ]; then
        cp "$OUT/client_$_id.pem" "$OUT/client.pem"
        cp "$OUT/client_${_id}_key.pem" "$OUT/client_key.pem"
        _first=0
    fi
done

echo "mtls_provision: local CA + server cert ($SERVER_CN) + client cert(s) [$*] in $OUT (rsa:$BITS/$SIG)"
