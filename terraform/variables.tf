variable "region" {
  description = "Main region for the pipeline."
  type        = string
  default     = "eu-west-2"
}

variable "receiving_region" {
  description = "Region for SES email receiving (must support inbound email)."
  type        = string
  default     = "eu-west-1"
}

variable "name" {
  description = "Prefix for every resource name."
  type        = string
  default     = "job-radar"
}

variable "mail_domain" {
  description = "Subdomain used to send the digest and receive job-alert emails."
  type        = string
  default     = "jobs.mustaphaseriki.dev"
}

variable "digest_recipient" {
  description = "Where the daily digest is sent. Must be verified while SES is in the sandbox."
  type        = string
  sensitive   = true
}

variable "alarm_email" {
  description = "Where failure alarms are sent (confirm the SNS subscription email once)."
  type        = string
  sensitive   = true
}

variable "schedule" {
  description = "When the daily run starts (EventBridge Scheduler cron)."
  type        = string
  default     = "cron(0 7 * * ? *)"
}

variable "job_ttl_days" {
  description = "How long a seen job is remembered before DynamoDB deletes it."
  type        = number
  default     = 30
}

variable "searches" {
  description = "Saved searches the daily run uses. radius_miles is converted to km for Adzuna."
  type = object({
    keywords        = list(string)
    exclude_words   = list(string)
    locations       = list(object({ name = string, radius_miles = number }))
    include_remote  = bool
    min_salary      = number
    min_day_rate    = number
    watch_companies = list(string)
  })
  default = {
    keywords      = ["DevOps Engineer", "Platform Engineer", "Site Reliability Engineer", "Cloud Engineer", "AWS Engineer"]
    exclude_words = ["trainee", "no experience", "career change", "graduate scheme"]
    locations = [
      { name = "Manchester", radius_miles = 40 },
      { name = "London", radius_miles = 25 },
      { name = "Birmingham", radius_miles = 25 },
    ]
    include_remote  = true
    min_salary      = 45000
    min_day_rate    = 400
    watch_companies = []
  }
}

variable "log_retention_days" {
  type    = number
  default = 14
}
