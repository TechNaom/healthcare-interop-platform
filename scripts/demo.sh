#!/usr/bin/env bash
# One-command local demo: generate throwaway keys, bring up Postgres + gateway,
# run migrations, and exercise create/read/search. LOCAL DEV ONLY — the keys
# generated here are ephemeral; production secrets come from Vault.
#
#   ./scripts/demo.sh          # start stack + run demo
#   ./scripts/demo.sh down     # tear everything down
set -euo pipefail
cd "$(dirname "$0")/.."

if [ "${1:-}" = "down" ]; then
    docker compose down -v
    exit 0
fi

if [ ! -f .env ]; then
    echo "==> generating .env with fresh local-only keys"
    fernet=$(uv run python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())")
    cat > .env <<EOF
POSTGRES_USER=hip
POSTGRES_PASSWORD=$(openssl rand -hex 16)
POSTGRES_DB=hip
HIP_ENCRYPTION_KEY=${fernet}
HIP_BLIND_INDEX_KEY=$(openssl rand -hex 32)
HIP_JWT_SECRET=$(openssl rand -hex 32)
KEYCLOAK_ADMIN=admin
KEYCLOAK_ADMIN_PASSWORD=$(openssl rand -hex 16)
VAULT_DEV_ROOT_TOKEN=$(openssl rand -hex 16)
MINIO_ROOT_USER=hip
MINIO_ROOT_PASSWORD=$(openssl rand -hex 16)
EOF
fi

echo "==> building and starting db + gateway"
docker compose up -d --build db app

echo "==> waiting for the gateway to become healthy"
until [ "$(docker inspect -f '{{.State.Health.Status}}' "$(docker compose ps -q app)" 2>/dev/null)" = "healthy" ]; do
    sleep 2
done

echo "==> running the demo (create / read / search a Patient)"
# shellcheck disable=SC1091
set -a; . ./.env; set +a
uv run python scripts/demo.py

echo "==> done. Tear down with: ./scripts/demo.sh down"
