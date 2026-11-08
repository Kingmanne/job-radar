# ---------- job-alert emails from LinkedIn, Indeed, Totaljobs and others ----------
# MX for jobs.mustaphaseriki.dev -> inbound-smtp.eu-west-1.amazonaws.com (output).
# SES stores each email in S3; S3 triggers the ingest Lambda, which writes the
# jobs into the London table with digest_pending set.

resource "aws_sesv2_email_identity" "domain_receiving" {
  provider       = aws.ireland
  email_identity = var.mail_domain
}

resource "aws_s3_bucket" "inbox" {
  provider      = aws.ireland
  bucket        = "${var.name}-inbox-${data.aws_caller_identity.current.account_id}"
  force_destroy = true
}

resource "aws_s3_bucket_public_access_block" "inbox" {
  provider                = aws.ireland
  bucket                  = aws_s3_bucket.inbox.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_server_side_encryption_configuration" "inbox" {
  provider = aws.ireland
  bucket   = aws_s3_bucket.inbox.id
  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}

resource "aws_s3_bucket_lifecycle_configuration" "inbox" {
  provider = aws.ireland
  bucket   = aws_s3_bucket.inbox.id
  rule {
    id     = "expire-raw-emails"
    status = "Enabled"
    filter {}
    expiration {
      days = 14
    }
  }
}

resource "aws_s3_bucket_policy" "inbox" {
  provider = aws.ireland
  bucket   = aws_s3_bucket.inbox.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid       = "AllowSESPuts"
        Effect    = "Allow"
        Principal = { Service = "ses.amazonaws.com" }
        Action    = "s3:PutObject"
        Resource  = "${aws_s3_bucket.inbox.arn}/incoming/*"
        Condition = {
          StringEquals = { "aws:SourceAccount" = data.aws_caller_identity.current.account_id }
          ArnLike      = { "aws:SourceArn" = "arn:aws:ses:${var.receiving_region}:${data.aws_caller_identity.current.account_id}:receipt-rule-set/${var.name}:receipt-rule/*" }
        }
      },
      {
        Sid       = "TLSOnly"
        Effect    = "Deny"
        Principal = "*"
        Action    = "s3:*"
        Resource  = [aws_s3_bucket.inbox.arn, "${aws_s3_bucket.inbox.arn}/*"]
        Condition = { Bool = { "aws:SecureTransport" = "false" } }
      }
    ]
  })
}

resource "aws_ses_receipt_rule_set" "main" {
  provider      = aws.ireland
  rule_set_name = var.name
}

resource "aws_ses_active_receipt_rule_set" "main" {
  provider      = aws.ireland
  rule_set_name = aws_ses_receipt_rule_set.main.rule_set_name
}

resource "aws_ses_receipt_rule" "alerts" {
  provider      = aws.ireland
  name          = "store-job-alerts"
  rule_set_name = aws_ses_receipt_rule_set.main.rule_set_name
  recipients    = ["alerts@${var.mail_domain}"]
  enabled       = true
  scan_enabled  = true # spam and virus scanning
  tls_policy    = "Require"

  s3_action {
    bucket_name       = aws_s3_bucket.inbox.id
    object_key_prefix = "incoming/"
    position          = 1
  }

  depends_on = [aws_s3_bucket_policy.inbox]
}

# ---------- ingest Lambda (Ireland, writes to the London table) ----------

resource "aws_cloudwatch_log_group" "ingest" {
  provider          = aws.ireland
  name              = "/aws/lambda/${var.name}-ingest"
  retention_in_days = var.log_retention_days
}

resource "aws_iam_role" "ingest" {
  name = "${var.name}-ingest"
  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { Service = "lambda.amazonaws.com" }
      Action    = "sts:AssumeRole"
    }]
  })
}

resource "aws_iam_role_policy" "ingest" {
  name = "least-privilege"
  role = aws_iam_role.ingest.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect   = "Allow"
        Action   = ["logs:CreateLogStream", "logs:PutLogEvents"]
        Resource = "${aws_cloudwatch_log_group.ingest.arn}:*"
      },
      {
        Effect   = "Allow"
        Action   = "s3:GetObject"
        Resource = "${aws_s3_bucket.inbox.arn}/incoming/*"
      },
      {
        Effect   = "Allow"
        Action   = ["dynamodb:GetItem", "dynamodb:PutItem", "dynamodb:UpdateItem"]
        Resource = aws_dynamodb_table.jobs.arn
      }
    ]
  })
}

resource "aws_lambda_function" "ingest" {
  provider         = aws.ireland
  function_name    = "${var.name}-ingest"
  role             = aws_iam_role.ingest.arn
  runtime          = "python3.13"
  architectures    = ["arm64"]
  handler          = "jobradar.ingest.handler"
  filename         = data.archive_file.app.output_path
  source_code_hash = data.archive_file.app.output_base64sha256
  timeout          = 60
  memory_size      = 256

  environment {
    variables = {
      TABLE_NAME   = aws_dynamodb_table.jobs.name
      TABLE_REGION = var.region
      JOB_TTL_DAYS = tostring(var.job_ttl_days)
    }
  }

  depends_on = [aws_cloudwatch_log_group.ingest, aws_iam_role_policy.ingest]
}

resource "aws_lambda_permission" "s3_invoke" {
  provider       = aws.ireland
  statement_id   = "AllowS3Invoke"
  action         = "lambda:InvokeFunction"
  function_name  = aws_lambda_function.ingest.function_name
  principal      = "s3.amazonaws.com"
  source_arn     = aws_s3_bucket.inbox.arn
  source_account = data.aws_caller_identity.current.account_id
}

resource "aws_s3_bucket_notification" "inbox" {
  provider = aws.ireland
  bucket   = aws_s3_bucket.inbox.id

  lambda_function {
    lambda_function_arn = aws_lambda_function.ingest.arn
    events              = ["s3:ObjectCreated:*"]
    filter_prefix       = "incoming/"
  }

  depends_on = [aws_lambda_permission.s3_invoke]
}
