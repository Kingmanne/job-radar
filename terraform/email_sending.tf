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
