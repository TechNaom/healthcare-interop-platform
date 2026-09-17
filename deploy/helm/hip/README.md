# HIP Helm chart

Deploys the FHIR gateway + HL7 MLLP listener to Kubernetes. Migrations run as a
`pre-install`/`pre-upgrade` Job. No cloud-vendor dependency — point it at the
client's own Postgres and secret store (ADR-003).

## Install

```bash
helm upgrade --install hip deploy/helm/hip \
  --set database.existingSecret=hip-db \        # Secret with key: database-url
  --set secrets.existingSecret=hip-secrets \    # Secret with keys: encryption-key, blind-index-key, jwt-secret
  --set image.tag=<built-image-tag>
```

For a quick non-prod trial you can pass values inline instead of `existingSecret`
(`--set database.url=...`, `--set secrets.encryptionKey=...`), but real secrets
must come from Vault / External Secrets, never from values or git.

## What it creates

- **gateway** Deployment + Service (`/healthz` `/readyz` probes; optional HPA).
- **mllp** Deployment + Service (HL7 v2 on port 2575).
- **migrate** Job (`alembic upgrade head`) as a pre-upgrade hook.
- Optional **Ingress** for the gateway.
- Secrets are referenced from `existingSecret`; inline Secrets are rendered only
  for non-prod convenience.

## Verify

```bash
helm lint deploy/helm/hip
helm template hip deploy/helm/hip            # render with defaults
```
