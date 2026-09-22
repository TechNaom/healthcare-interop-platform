# Cloud-native reference: provisions the managed pieces the HIP chart's
# values-cloud.yaml expects, on AWS. This is a REFERENCE the client adapts and
# applies in THEIR OWN account under THEIR BAA (ADR-005): TechNaom never hosts
# client PHI. GCP/Azure equivalents are parallel (Cloud SQL / Azure DB for
# Postgres; Secret Manager / Key Vault) — the app is identical, only these
# managed resources differ.
#
# Scope: managed Postgres (RDS) + the app secrets in Secrets Manager. The
# Kubernetes deployment itself is the Helm chart (deploy/helm/hip) with
# values-cloud.yaml; run it after apply, wiring database.existingSecret /
# secrets.existingSecret to Secrets synced by External Secrets Operator from the
# ARNs output below.
#
# NOTE: unverified scaffolding — no `terraform` in the build environment to run
# `terraform validate`/`plan`. Review before use; pin provider versions to your
# org's baseline.

terraform {
  required_version = ">= 1.6"
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
    random = {
      source  = "hashicorp/random"
      version = "~> 3.6"
    }
  }
}

provider "aws" {
  region = var.region
}

# --- Managed Postgres (swaps the self-hosted `db` service) ------------------ #
resource "random_password" "db" {
  length  = 32
  special = false
}

resource "aws_db_subnet_group" "hip" {
  name       = "${var.name}-db"
  subnet_ids = var.private_subnet_ids
  tags       = var.tags
}

resource "aws_db_instance" "hip" {
  identifier                 = "${var.name}-pg"
  engine                     = "postgres"
  engine_version             = var.postgres_version
  instance_class             = var.db_instance_class
  allocated_storage          = var.db_allocated_storage
  db_name                    = "hip"
  username                   = "hip"
  password                   = random_password.db.result
  db_subnet_group_name       = aws_db_subnet_group.hip.name
  vpc_security_group_ids     = var.db_security_group_ids
  storage_encrypted          = true # PHI at rest (HIPAA 164.312(a)(2)(iv))
  multi_az                   = var.db_multi_az
  backup_retention_period    = var.db_backup_retention_days
  deletion_protection        = true
  auto_minor_version_upgrade = true
  skip_final_snapshot        = false
  final_snapshot_identifier  = "${var.name}-pg-final"
  tags                       = var.tags
}

# --- App secrets (swaps Vault; synced into the cluster by External Secrets) - #
# Encryption + blind-index keys. The gateway validates tokens via the managed
# OIDC provider's JWKS (helm config.jwtJwksUrl), so no JWT secret is stored.
resource "random_password" "encryption_key" {
  length  = 32
  special = false
}

resource "random_password" "blind_index_key" {
  length  = 48
  special = false
}

resource "aws_secretsmanager_secret" "db" {
  name       = "${var.name}/database-url"
  kms_key_id = var.secrets_kms_key_id
  tags       = var.tags
}

resource "aws_secretsmanager_secret_version" "db" {
  secret_id = aws_secretsmanager_secret.db.id
  # SQLAlchemy async URL — the exact string the app reads as HIP_DATABASE_URL.
  secret_string = jsonencode({
    "database-url" = "postgresql+asyncpg://hip:${random_password.db.result}@${aws_db_instance.hip.address}:5432/hip"
  })
}

resource "aws_secretsmanager_secret" "app" {
  name       = "${var.name}/app-secrets"
  kms_key_id = var.secrets_kms_key_id
  tags       = var.tags
}

resource "aws_secretsmanager_secret_version" "app" {
  secret_id = aws_secretsmanager_secret.app.id
  secret_string = jsonencode({
    "encryption-key"  = random_password.encryption_key.result
    "blind-index-key" = random_password.blind_index_key.result
  })
}
