# One item per job. pk = "<source>#<job id>".
# A job waiting for the next digest carries `digest_pending`, which puts it
# in the sparse GSI; the daily run removes the attribute once it is emailed.
resource "aws_dynamodb_table" "jobs" {
  name         = "${var.name}-jobs"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "pk"

  attribute {
    name = "pk"
    type = "S"
  }
  attribute {
    name = "digest_pending"
    type = "S"
  }
  attribute {
    name = "score"
    type = "N"
  }

  global_secondary_index {
    name            = "pending-by-score"
    hash_key        = "digest_pending"
    range_key       = "score"
    projection_type = "ALL"
  }

  ttl {
    attribute_name = "expires_at"
    enabled        = true
  }

  point_in_time_recovery {
    enabled = true
  }

  server_side_encryption {
    enabled = true
  }
}

# API keys. Terraform creates placeholders only; set the real values once with
#   aws ssm put-parameter --name /job-radar/reed_api_key --type SecureString --overwrite --value '...'
# so the secrets never enter Terraform state or Git.
resource "aws_ssm_parameter" "api_keys" {
  for_each = toset(["reed_api_key", "adzuna_app_id", "adzuna_app_key", "cvlibrary_api_key"])

  name  = "/${var.name}/${each.key}"
  type  = "SecureString"
  value = "CHANGE_ME"

  lifecycle {
    ignore_changes = [value]
  }
}

# Search settings, readable without a redeploy.
resource "aws_ssm_parameter" "searches" {
  name  = "/${var.name}/searches"
  type  = "String"
  value = jsonencode(var.searches)
}

# Failed async invocations land here instead of disappearing.
resource "aws_sqs_queue" "dlq" {
  name                      = "${var.name}-dlq"
  message_retention_seconds = 1209600 # 14 days
  sqs_managed_sse_enabled   = true
}
