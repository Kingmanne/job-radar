# Send the digest from radar@jobs.mustaphaseriki.dev (DKIM-signed), so it
# doesn't land in spam. The DKIM CNAMEs are printed as outputs: add them in
# Cloudflare once (DNS only).
resource "aws_sesv2_email_identity" "domain" {
  email_identity = var.mail_domain
}

# While SES is in the sandbox it only sends to verified addresses.
# AWS emails a confirmation link to this address: click it once.
resource "aws_sesv2_email_identity" "recipient" {
  email_identity = var.digest_recipient
}
# Bounces come from bounce.jobs.mustaphaseriki.dev instead of amazonses.com,
# so SPF passes for our own domain (Outlook and Gmail trust this more).
resource "aws_sesv2_email_identity_mail_from_attributes" "domain" {
  email_identity         = aws_sesv2_email_identity.domain.email_identity
  mail_from_domain       = "bounce.${var.mail_domain}"
  behavior_on_mx_failure = "USE_DEFAULT_VALUE"
}