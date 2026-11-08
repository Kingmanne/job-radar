data "aws_caller_identity" "current" {}

data "archive_file" "app" {
  type        = "zip"
  source_dir  = "${path.module}/../src"
  output_path = "${path.module}/build/app.zip"
  excludes    = ["**/__pycache__/**"]
}

# ---------- daily run: fetch -> dedupe -> filter -> score -> digest ----------

resource "aws_cloudwatch_log_group" "daily" {
  name              = "/aws/lambda/${var.name}-daily"
  retention_in_days = var.log_retention_days
}

resource "aws_iam_role" "daily" {
  name = "${var.name}-daily"
  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { Service = "lambda.amazonaws.com" }
      Action    = "sts:AssumeRole"
    }]
  })
}

resource "aws_iam_role_policy" "daily" {
  name = "least-privilege"
  role = aws_iam_role.daily.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid      = "Logs"
        Effect   = "Allow"
        Action   = ["logs:CreateLogStream", "logs:PutLogEvents"]
        Resource = "${aws_cloudwatch_log_group.daily.arn}:*"
      },
      {
        Sid      = "JobsTable"
        Effect   = "Allow"
        Action   = ["dynamodb:GetItem", "dynamodb:PutItem", "dynamodb:UpdateItem", "dynamodb:BatchGetItem", "dynamodb:BatchWriteItem", "dynamodb:Query"]
        Resource = [aws_dynamodb_table.jobs.arn, "${aws_dynamodb_table.jobs.arn}/index/*"]
      },
      {
        Sid      = "ReadSettingsAndKeys"
        Effect   = "Allow"
        Action   = ["ssm:GetParameter", "ssm:GetParameters", "ssm:GetParametersByPath"]
        Resource = "arn:aws:ssm:${var.region}:${data.aws_caller_identity.current.account_id}:parameter/${var.name}/*"
      },
      {
        Sid       = "DecryptKeys"
        Effect    = "Allow"
        Action    = "kms:Decrypt"
        Resource  = "*" # the AWS-managed aws/ssm key, only when called through SSM
        Condition = { StringEquals = { "kms:ViaService" = "ssm.${var.region}.amazonaws.com" } }
      },
      {
        Sid       = "SendDigest"
        Effect    = "Allow"
        Action    = ["ses:SendEmail", "ses:SendRawEmail"]
        Resource  = "*"
        Condition = { StringEquals = { "ses:FromAddress" = "radar@${var.mail_domain}" } }
      },
      {
        Sid      = "DeadLetter"
        Effect   = "Allow"
        Action   = "sqs:SendMessage"
        Resource = aws_sqs_queue.dlq.arn
      }
    ]
  })
}

resource "aws_lambda_function" "daily" {
  function_name    = "${var.name}-daily"
  role             = aws_iam_role.daily.arn
  runtime          = "python3.13"
  architectures    = ["arm64"]
  handler          = "jobradar.daily.handler"
  filename         = data.archive_file.app.output_path
  source_code_hash = data.archive_file.app.output_base64sha256
  timeout          = 300
  memory_size      = 512

  environment {
    variables = {
      TABLE_NAME   = aws_dynamodb_table.jobs.name
      PARAM_PREFIX = "/${var.name}"
      DIGEST_FROM  = "Job Radar <radar@${var.mail_domain}>"
      DIGEST_TO    = var.digest_recipient
      JOB_TTL_DAYS = tostring(var.job_ttl_days)
    }
  }

  dead_letter_config {
    target_arn = aws_sqs_queue.dlq.arn
  }

  depends_on = [aws_cloudwatch_log_group.daily, aws_iam_role_policy.daily]
}

# ---------- schedule ----------

resource "aws_iam_role" "scheduler" {
  name = "${var.name}-scheduler"
  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { Service = "scheduler.amazonaws.com" }
      Action    = "sts:AssumeRole"
      Condition = { StringEquals = { "aws:SourceAccount" = data.aws_caller_identity.current.account_id } }
    }]
  })
}

resource "aws_iam_role_policy" "scheduler" {
  name = "invoke-daily"
  role = aws_iam_role.scheduler.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect   = "Allow"
      Action   = "lambda:InvokeFunction"
      Resource = aws_lambda_function.daily.arn
    }]
  })
}

resource "aws_scheduler_schedule" "daily" {
  name                         = "${var.name}-daily"
  schedule_expression          = var.schedule
  schedule_expression_timezone = "Europe/London" # follows BST/GMT automatically

  flexible_time_window {
    mode = "OFF"
  }

  target {
    arn      = aws_lambda_function.daily.arn
    role_arn = aws_iam_role.scheduler.arn

    retry_policy {
      maximum_retry_attempts       = 2
      maximum_event_age_in_seconds = 3600
    }
  }
}
