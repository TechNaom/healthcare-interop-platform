# Cloud-native deployment

The platform is **cloud-agnostic by construction** (ADR-003): the self-hosted
stack and a managed-cloud deployment run the *same* OCI image and differ only in
configuration. There is no separate cloud codebase — each self-hosted component
is behind an interface or an env var, so a managed service swaps in without a
code change.

## The config seam

| Concern | Self-hosted (default) | Managed / cloud | Swapped via |
|---|---|---|---|
| Database | `db` Postgres container | RDS / Cloud SQL / Azure DB for Postgres | `HIP_DATABASE_URL` |
| Encryption + blind-index keys | Vault or env | Cloud secret manager → Secret (External Secrets) | `HIP_ENCRYPTION_KEY` / `HIP_BLIND_INDEX_KEY`, or `HIP_VAULT_*` |
| Identity / token validation | Keycloak (HS256 secret or JWKS) | Managed OIDC (Cognito/Entra/Keycloak) via JWKS | `HIP_JWT_JWKS_URL` |
| Object storage (when needed) | MinIO | S3 / GCS / Azure Blob | `security.objectstore` interface (no consumer yet) |

Because the app only reads these env vars, the "cloud-native variant" is
**deployment artifacts + configuration**, not a code fork:

- [deploy/helm/hip/values-cloud.yaml](../deploy/helm/hip/values-cloud.yaml) — the
  Helm overlay: managed DB via `existingSecret`, keys via `existingSecret`,
  token validation via `config.jwtJwksUrl` (no shared JWT secret stored),
  autoscaling + ingress + TLS on.
- [deploy/terraform/aws](../deploy/terraform/aws) — a reference module
  provisioning the managed pieces (RDS Postgres with encryption-at-rest, the app
  secrets in Secrets Manager). GCP/Azure equivalents are parallel.

## Deploy (AWS reference)

```bash
# 1. Provision managed Postgres + secrets in the CLIENT's account.
cd deploy/terraform/aws
terraform init && terraform apply -var region=us-east-1 \
  -var 'private_subnet_ids=[...]' -var 'db_security_group_ids=[...]'

# 2. Sync the Secrets Manager entries into the cluster (External Secrets
#    Operator) as Secrets named hip-db and hip-secrets.

# 3. Deploy the SAME image via Helm with the cloud overlay.
helm upgrade --install hip deploy/helm/hip -f deploy/helm/hip/values-cloud.yaml \
  --set image.repository=<registry>/healthcare-interop-platform-app \
  --set image.tag=<tag> \
  --set config.jwtJwksUrl=https://<oidc-issuer>/protocol/openid-connect/certs
```

## The hard constraint

**TechNaom never hosts client PHI.** The cloud-native path is for the *client*
to deploy in *their own* cloud account, under *their own* BAA (ADR-005). Hosting
PHI in TechNaom's cloud would make TechNaom a business associate with the
attendant liability — out of scope. Dev/test always uses local ephemeral
Postgres with synthetic data only, never a cloud database.

## Status

The application code and Helm chart support this today (the JWKS seam and
Vault/env key sourcing are implemented and tested). The Terraform module is a
reviewed **reference** — it has not been `terraform apply`-ed from this repo and
must be adapted to the client's VPC/networking and provider-version baseline
before use.
