output "db_endpoint" {
  description = "Managed Postgres endpoint."
  value       = aws_db_instance.hip.address
}

output "database_url_secret_arn" {
  description = "Secrets Manager ARN holding database-url (wire to database.existingSecret via External Secrets)."
  value       = aws_secretsmanager_secret.db.arn
}

output "app_secrets_arn" {
  description = "Secrets Manager ARN holding encryption-key + blind-index-key (wire to secrets.existingSecret)."
  value       = aws_secretsmanager_secret.app.arn
}
