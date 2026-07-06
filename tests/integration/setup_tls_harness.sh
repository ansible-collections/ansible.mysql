#!/usr/bin/env bash
set -euo pipefail

if [[ $# -lt 2 ]]; then
    echo "Usage: $0 <docker|podman> <container> [container...]" >&2
    exit 1
fi

runtime="$1"
shift
containers=("$@")

tmpdir="$(mktemp -d)"
cleanup() {
    rm -rf "$tmpdir"
}
trap cleanup EXIT

cat >"$tmpdir/openssl.cnf" <<'EOF'
[req]
distinguished_name = req_distinguished_name
x509_extensions = v3_req
prompt = no

[req_distinguished_name]
CN = localhost

[v3_req]
basicConstraints = critical,CA:TRUE
keyUsage = critical,digitalSignature,keyEncipherment,keyCertSign
extendedKeyUsage = serverAuth
subjectAltName = @alt_names

[alt_names]
DNS.1 = localhost
IP.1 = 127.0.0.1
EOF

openssl req -x509 -nodes -newkey rsa:2048 \
    -keyout "$tmpdir/server-key.pem" \
    -out "$tmpdir/server-cert.pem" \
    -days 1 \
    -config "$tmpdir/openssl.cnf" >/dev/null 2>&1

cp "$tmpdir/server-cert.pem" "$tmpdir/ca.pem"

for container in "${containers[@]}"; do
    "$runtime" exec "$container" sh -c 'mkdir -p /etc/mysql/tls'
    "$runtime" cp "$tmpdir/server-cert.pem" "$container:/etc/mysql/tls/server-cert.pem"
    "$runtime" cp "$tmpdir/server-key.pem" "$container:/etc/mysql/tls/server-key.pem"
    "$runtime" cp "$tmpdir/ca.pem" "$container:/etc/mysql/tls/ca.pem"

    printf '%s\n' \
        '[mysqld]' \
        'ssl_ca=/etc/mysql/tls/ca.pem' \
        'ssl_cert=/etc/mysql/tls/server-cert.pem' \
        'ssl_key=/etc/mysql/tls/server-key.pem' \
        'require_secure_transport=OFF' \
        | "$runtime" exec -i "$container" sh -c 'cat > /etc/mysql/conf.d/tls.cnf'

    "$runtime" exec "$container" sh -c \
        'chown mysql:mysql /etc/mysql/tls/ca.pem /etc/mysql/tls/server-cert.pem /etc/mysql/tls/server-key.pem && chmod 0644 /etc/mysql/tls/ca.pem /etc/mysql/tls/server-cert.pem && chmod 0600 /etc/mysql/tls/server-key.pem'
done
