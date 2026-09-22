variable "name" {
  description = "Name prefix for provisioned resources."
  type        = string
  default     = "hip"
}

variable "region" {
  description = "AWS region."
  type        = string
}

variable "tags" {
  description = "Tags applied to all resources (add your data-classification tags)."
  type        = map(string)
  default     = {}
}

variable "private_subnet_ids" {
  description = "Private subnet IDs for the DB subnet group (no public exposure)."
  type        = list(string)
}

variable "db_security_group_ids" {
  description = "Security groups allowing the cluster to reach Postgres on 5432."
  type        = list(string)
}

variable "postgres_version" {
  description = "Managed Postgres engine version (match the app's tested major, 16)."
  type        = string
  default     = "16"
}

variable "db_instance_class" {
  type    = string
  default = "db.t3.medium"
}

variable "db_allocated_storage" {
  type    = number
  default = 50
}

variable "db_multi_az" {
  description = "Multi-AZ for HA (recommended for production PHI workloads)."
  type        = bool
  default     = true
}

variable "db_backup_retention_days" {
  type    = number
  default = 14
}

variable "secrets_kms_key_id" {
  description = "Customer-managed KMS key for Secrets Manager (null = AWS-managed)."
  type        = string
  default     = null
}
