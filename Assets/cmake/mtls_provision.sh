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
#                     [--san <dns-or-ip>]... [--clients-file <path>]
#
# Defaults: server_CN = "localhost"; a single client identity "harpia-client"
# when none is named (neither positionally nor in a --clients-file).
#
# Options (multi-system-reference / reference-system task 1, additive -- the
# positional form above is unchanged; options may appear anywhere after
# <out_dir>):
#   --san <dns-or-ip>    extra server subjectAltName beyond <server_CN>,
#                        localhost and 127.0.0.1 (repeatable): a LAN IP, a
#                        hostname, 10.0.2.2 for the Android emulator. An IPv4
#                        or IPv6 literal becomes an IP: entry, anything else
#                        a DNS: entry.
#   --clients-file <f>   one "<identity> <role>" per line (role: admin | main |
#                        guest; blank lines and '#' comment lines skipped).
#                        Issues one client cert per identity and writes
#                        rbac_map.txt (the HARPIA_RBAC_MAP format: "<CN> <role>"
#                        per line) for exactly those identities. Identities
#                        are [A-Za-z0-9._-] only (they become file names and
#                        certificate CNs).
#
# Re-runs are idempotent: an existing CA (ca.pem + ca_key.pem) is reused and
# an existing client identity (client_<id>.pem signed by that CA) is kept, not
# re-keyed -- so thousands of identities can be extended incrementally and
# certificates already copied to devices stay valid. The server certificate
# IS re-issued on every run (from the same CA), so --san changes take effect.
# Issuing is parallel (HARPIA_MTLS_JOBS, default: number of CPUs).
#
# Produces in <out_dir>:
#   ca.pem                      local CA cert -- trust anchor for BOTH the
#                               server (client verifying the server) and the
#                               clients (server verifying the client)
#   ca_key.pem                  its private key (used only to sign, here)
#   server.pem                  server identity cert: EKU serverAuth,
#                               SAN = <server_CN>, localhost, 127.0.0.1, --san...
#   server_key.pem              its private key
#   client.pem                  first client identity cert: EKU clientAuth,
#                               subject CN = the identity name (this is the
#                               string task 4 maps to a role)
#   client_key.pem              its private key
#   client_<identity>.pem       every client identity, one cert/key pair each
#   client_<identity>_key.pem
#   rbac_map.txt                only with --clients-file (see above)
set -eu

usage() {
    echo "usage: $0 <out_dir> [server_CN] [client_identity ...] [--san <dns-or-ip>]... [--clients-file <path>]" >&2
    exit 2
}

if [ $# -lt 1 ]; then
    usage
fi

OUT=$1
shift

# split options from positionals (POSIX sh: no arrays, so the positionals are
# collected newline-separated; identities can't contain whitespace anyway)
SANS=""
CLIENTS_FILE=""
POS=""
while [ $# -gt 0 ]; do
    case "$1" in
        --san)
            [ $# -ge 2 ] || usage
            SANS="$SANS $2"; shift 2 ;;
        --clients-file)
            [ $# -ge 2 ] || usage
            CLIENTS_FILE=$2; shift 2 ;;
        --*) echo "mtls_provision: unknown option $1" >&2; usage ;;
        *)  POS="$POS
$1"; shift ;;
    esac
done
# before anything else needs an external tool (sed/awk/openssl)
command -v openssl >/dev/null 2>&1 || { echo "mtls_provision: openssl not found" >&2; exit 3; }
POS=$(printf '%s\n' "$POS" | sed '/^$/d')

SERVER_CN=$(printf '%s\n' "$POS" | sed -n '1p')
[ -n "$SERVER_CN" ] || SERVER_CN=localhost
IDS=$(printf '%s\n' "$POS" | sed -n '2,$p')


case "${HARPIA_MTLS_PROVIDER:-default}" in
    fips) BITS=3072; SIG=sha384 ;;
    *)    BITS=2048; SIG=sha256 ;;
esac

mkdir -p "$OUT"

valid_id() {
    case "$1" in
        ''|*[!A-Za-z0-9._-]*) return 1 ;;
        *) return 0 ;;
    esac
}

# --clients-file: validate every line up front (all-or-nothing), collect the
# identities and the rbac map.
MAP=""
if [ -n "$CLIENTS_FILE" ]; then
    [ -r "$CLIENTS_FILE" ] || { echo "mtls_provision: cannot read $CLIENTS_FILE" >&2; exit 2; }
    _n=0
    while IFS= read -r _line || [ -n "$_line" ]; do
        _n=$((_n + 1))
        _line=$(printf '%s' "$_line" | tr -d '\r')
        case "$_line" in ''|'#'*) continue ;; esac
        # shellcheck disable=SC2086
        set -- $_line
        if [ $# -ne 2 ] || ! valid_id "$1"; then
            echo "mtls_provision: $CLIENTS_FILE:$_n: expected '<identity> <role>' with identity in [A-Za-z0-9._-]" >&2
            exit 2
        fi
        case "$2" in admin|main|guest) ;; *)
            echo "mtls_provision: $CLIENTS_FILE:$_n: role must be admin, main or guest (got '$2')" >&2
            exit 2 ;;
        esac
        IDS="$IDS
$1"
        MAP="$MAP$1 $2
"
    done < "$CLIENTS_FILE"
fi
IDS=$(printf '%s\n' "$IDS" | sed '/^$/d' | awk '!seen[$0]++')
[ -n "$IDS" ] || IDS=harpia-client
for _id in $IDS; do
    valid_id "$_id" || { echo "mtls_provision: invalid identity '$_id'" >&2; exit 2; }
done

# 1. local CA -- the single trust anchor for both directions of the handshake.
#    Reused when present, so existing identities stay valid.
if [ -s "$OUT/ca.pem" ] && [ -s "$OUT/ca_key.pem" ]; then
    CA_STATE="reused"
else
    openssl req -x509 -nodes -newkey "rsa:$BITS" "-$SIG" -days 3650 \
        -keyout "$OUT/ca_key.pem" -out "$OUT/ca.pem" \
        -subj "/O=harpia/CN=harpia-local-mtls-ca" >/dev/null 2>&1
    CA_STATE="new"
fi

# issue <basename> <subject> <extfile-contents>
#   signs a fresh key + CSR with the CA and the given x509 extensions. Safe to
#   run concurrently for different basenames (per-cert temp files, random
#   serials instead of the shared ca.srl file).
issue() {
    _base=$1
    _subj=$2
    _ext=$3
    _extf="$OUT/$_base.ext"
    printf '%s\n' "$_ext" > "$_extf"
    openssl req -nodes -newkey "rsa:$BITS" "-$SIG" \
        -keyout "$OUT/${_base}_key.pem" -out "$OUT/$_base.csr" \
        -subj "$_subj" >/dev/null 2>&1
    _serial=0x$(openssl rand -hex 16)
    openssl x509 -req -in "$OUT/$_base.csr" -days 3650 "-$SIG" \
        -CA "$OUT/ca.pem" -CAkey "$OUT/ca_key.pem" -set_serial "$_serial" \
        -extfile "$_extf" -out "$OUT/$_base.pem.tmp" >/dev/null 2>&1
    mv "$OUT/$_base.pem.tmp" "$OUT/$_base.pem"
    rm -f "$OUT/$_base.csr" "$_extf"
}

# 2. server identity -- serverAuth + SAN (modern TLS stacks reject a bare CN).
#    Re-issued every run so --san changes apply.
SAN_EXT="DNS:$SERVER_CN,DNS:localhost,IP:127.0.0.1"
for _s in $SANS; do
    case "$_s" in
        *:*|*[!0-9.]*) case "$_s" in *:*) SAN_EXT="$SAN_EXT,IP:$_s" ;; *) SAN_EXT="$SAN_EXT,DNS:$_s" ;; esac ;;
        *) SAN_EXT="$SAN_EXT,IP:$_s" ;;
    esac
done
issue server "/O=harpia/CN=$SERVER_CN" \
"basicConstraints=CA:FALSE
keyUsage=digitalSignature,keyEncipherment
extendedKeyUsage=serverAuth
subjectAltName=$SAN_EXT"

# 3. one client identity per name, issued in parallel; an identity whose cert
#    already exists and verifies against this CA is kept as-is. The first is
#    also written as the unqualified client.pem / client_key.pem the generated
#    demo client and the task-2/3 integration tests pick up without needing to
#    know the identity name.
JOBS=${HARPIA_MTLS_JOBS:-$(getconf _NPROCESSORS_ONLN 2>/dev/null || echo 4)}
_running=0
_new=0
_kept=0
for _id in $IDS; do
    if [ -s "$OUT/client_$_id.pem" ] && [ -s "$OUT/client_${_id}_key.pem" ] &&
       openssl verify -CAfile "$OUT/ca.pem" "$OUT/client_$_id.pem" >/dev/null 2>&1; then
        _kept=$((_kept + 1))
        continue
    fi
    issue "client_$_id" "/O=harpia/CN=$_id" \
"basicConstraints=CA:FALSE
keyUsage=digitalSignature,keyEncipherment
extendedKeyUsage=clientAuth" &
    _new=$((_new + 1))
    _running=$((_running + 1))
    if [ "$_running" -ge "$JOBS" ]; then
        wait
        _running=0
    fi
done
wait
# background jobs don't trip `set -e`: check every identity actually landed
for _id in $IDS; do
    if ! openssl verify -CAfile "$OUT/ca.pem" "$OUT/client_$_id.pem" >/dev/null 2>&1; then
        echo "mtls_provision: failed to issue client identity '$_id'" >&2
        exit 4
    fi
done

_first=$(printf '%s\n' "$IDS" | sed -n '1p')
cp "$OUT/client_$_first.pem" "$OUT/client.pem"
cp "$OUT/client_${_first}_key.pem" "$OUT/client_key.pem"

if [ -n "$CLIENTS_FILE" ]; then
    printf '%s' "$MAP" > "$OUT/rbac_map.txt"
fi

_count=$(printf '%s\n' "$IDS" | wc -l | tr -d ' ')
echo "mtls_provision: CA ($CA_STATE) + server cert ($SERVER_CN; SAN $SAN_EXT) + $_count client identit(y/ies) ($_new new, $_kept kept) in $OUT (rsa:$BITS/$SIG)"
