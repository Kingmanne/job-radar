# Not encrypted with the AWS-managed aws/sns key on purpose: CloudWatch alarms
# cannot publish to a topic using that key (its policy doesn't allow them).
#checkov:skip=CKV_AWS_26:alarm topic carries no sensitive data; aws/sns would block CloudWatch
resource "aws_sns_topic" "alarms" {
  name = "${var.name}-alarms"
}

# AWS emails a confirmation link: click it once.
resource "aws_sns_topic_subscription" "alarm_email" {
  topic_arn = aws_sns_topic.alarms.arn
  protocol  = "email"
  endpoint  = var.alarm_email
}

resource "aws_cloudwatch_metric_alarm" "daily_errors" {
  alarm_name          = "${var.name}-daily-errors"
  alarm_description   = "The daily Job Radar run failed."
  namespace           = "AWS/Lambda"
  metric_name         = "Errors"
  dimensions          = { FunctionName = aws_lambda_function.daily.function_name }
  statistic           = "Sum"
  period              = 3600
  evaluation_periods  = 1
  threshold           = 1
  comparison_operator = "GreaterThanOrEqualToThreshold"
  treat_missing_data  = "notBreaching"
  alarm_actions       = [aws_sns_topic.alarms.arn]
}

resource "aws_cloudwatch_metric_alarm" "dlq_not_empty" {
  alarm_name          = "${var.name}-dlq-not-empty"
  alarm_description   = "A Job Radar invocation failed after retries and is waiting in the DLQ."
  namespace           = "AWS/SQS"
  metric_name         = "ApproximateNumberOfMessagesVisible"
  dimensions          = { QueueName = aws_sqs_queue.dlq.name }
  statistic           = "Maximum"
  period              = 300
  evaluation_periods  = 1
  threshold           = 1
  comparison_operator = "GreaterThanOrEqualToThreshold"
  treat_missing_data  = "notBreaching"
  alarm_actions       = [aws_sns_topic.alarms.arn]
}

# The ingest alarm lives in Ireland with its own topic, because
# CloudWatch alarms can only notify an SNS topic in their own region.
#checkov:skip=CKV_AWS_26:alarm topic carries no sensitive data; aws/sns would block CloudWatch
resource "aws_sns_topic" "alarms_ireland" {
  provider = aws.ireland
  name     = "${var.name}-alarms"
}

resource "aws_sns_topic_subscription" "alarm_email_ireland" {
  provider  = aws.ireland
  topic_arn = aws_sns_topic.alarms_ireland.arn
  protocol  = "email"
  endpoint  = var.alarm_email
}

resource "aws_cloudwatch_metric_alarm" "ingest_errors" {
  provider            = aws.ireland
  alarm_name          = "${var.name}-ingest-errors"
  alarm_description   = "A job-alert email could not be parsed."
  namespace           = "AWS/Lambda"
  metric_name         = "Errors"
  dimensions          = { FunctionName = aws_lambda_function.ingest.function_name }
  statistic           = "Sum"
  period              = 3600
  evaluation_periods  = 1
  threshold           = 1
  comparison_operator = "GreaterThanOrEqualToThreshold"
  treat_missing_data  = "notBreaching"
  alarm_actions       = [aws_sns_topic.alarms_ireland.arn]
}
