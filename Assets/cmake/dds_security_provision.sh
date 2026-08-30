#!/bin/sh
# Configure-time helper for -DUSE_DDS_SECURITY=ON and the DDS-Security demo
# test (dds-transport epic, task 3) -- the DDS-Security analogue of
# Assets/cmake/curve_keygen_probe.cpp. Mints a THROWAWAY PKI and S/MIME-signs
# the governance/permissions documents so a secured DDS demo runs without
# hand-managed certificates.
#
#   NEVER for production. Real deployments provision identities from their own
#   CA / HSM and sign the governance/permissions with their own permissions
#   CA. This exists so the *demo* can prove "unauthenticated peers are
#   refused" end to end.
#
# Usage:
#   dds_security_provision.sh <out_dir> <governance.xml> <permissions.xml> [subject_CN]
#
# Produces in <out_dir>:
#   identity_ca.pem            throwaway CA cert (also the permissions CA)
#   identity_ca_key.pem        its private key (used only to sign here)
#   identity_certificate.pem   this participant's identity cert
#   private_key.pem            its private key
#   permissions_ca.pem         == identity_ca.pem
#   governance.p7s             S/MIME-signed <governance.xml>
#   permissions.p7s            S/MIME-signed <permissions.xml> with the
#                              %HARPIA_SUBJECT_NAME% sentinel replaced by the
#                              identity cert's real RFC2253 subject
set -eu

if [ $# -lt 3 ]; then
    echo "usage: $0 <out_dir> <governance.xml> <permissions.xml> [subject_CN]" >&2
    exit 2
fi

OUT=$1
GOV=$2
PERM=$3
CN=${4:-harpia-demo}

command -v openssl >/dev/null 2>&1 || { echo "dds_security_provision: openssl not found" >&2; exit 3; }
mkdir -p "$OUT"

# 1. throwaway CA -- also serves as the permissions CA for the demo.
openssl req -x509 -nodes -newkey rsa:2048 -days 3650 \
    -keyout "$OUT/identity_ca_key.pem" -out "$OUT/identity_ca.pem" \
    -subj "/O=harpia/CN=harpia-demo-ca" >/dev/null 2>&1
cp "$OUT/identity_ca.pem" "$OUT/permissions_ca.pem"

# 2. identity certificate for this participant, signed by the CA.
openssl req -nodes -newkey rsa:2048 \
    -keyout "$OUT/private_key.pem" -out "$OUT/identity.csr" \
    -subj "/O=harpia/CN=$CN" >/dev/null 2>&1
openssl x509 -req -in "$OUT/identity.csr" -days 3650 \
    -CA "$OUT/identity_ca.pem" -CAkey "$OUT/identity_ca_key.pem" -CAcreateserial \
    -out "$OUT/identity_certificate.pem" >/dev/null 2>&1
rm -f "$OUT/identity.csr" "$OUT/identity_ca.srl"

# 3. the permissions grant's <subject_name> must match the identity cert's
#    subject exactly. Read it back in RFC2253 form and substitute the
#    sentinel the rendered template carries, so formatting quirks between
#    OpenSSL and the DDS-Security plugin can't desync the two.
SUBJECT=$(openssl x509 -noout -subject -nameopt RFC2253 -in "$OUT/identity_certificate.pem" \
    | sed 's/^subject= *//; s/^subject=//')
PERM_RENDERED="$OUT/permissions.rendered.xml"
sed "s|%HARPIA_SUBJECT_NAME%|${SUBJECT}|g" "$PERM" > "$PERM_RENDERED"

# 4. S/MIME-sign governance + permissions with the CA. DDS-Security requires
#    PKCS#7-signed documents; the plugins reject unsigned XML. -nodetach so
#    the signed blob carries the content.
openssl smime -sign -in "$GOV" -text -nodetach \
    -signer "$OUT/identity_ca.pem" -inkey "$OUT/identity_ca_key.pem" \
    -out "$OUT/governance.p7s" >/dev/null 2>&1
openssl smime -sign -in "$PERM_RENDERED" -text -nodetach \
    -signer "$OUT/identity_ca.pem" -inkey "$OUT/identity_ca_key.pem" \
    -out "$OUT/permissions.p7s" >/dev/null 2>&1

echo "dds_security_provision: PKI + signed governance/permissions in $OUT (subject: $SUBJECT)"
