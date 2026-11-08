output "cloudflare_dns_records" {
  description = "Add these in Cloudflare for mustaphaseriki.dev, all DNS only (grey cloud)."
  value = concat(
    [{ type = "MX", name = var.mail_domain, value = "inbound-smtp.${var.receiving_region}.amazonaws.com", priority = 10 }],
    [for t in aws_sesv2_email_identity.domain.dkim_signing_attributes[0].tokens :
    { type = "CNAME", name = "${t}._domainkey.${var.mail_domain}", value = "${t}.dkim.amazonses.com", priority = null }],
    [for t in aws_sesv2_email_identity.domain_receiving.dkim_signing_attributes[0].tokens :
    { type = "CNAME", name = "${t}._domainkey.${var.mail_domain}", value = "${t}.dkim.amazonses.com", priority = null }]
  )
}

output "alert_address" {
  description = "Point job alerts on LinkedIn, Indeed, Totaljobs and others at this address."
  value       = "alerts@${var.mail_domain}"
}

output "set_api_keys" {
  description = "Run once per key to store the real value."
  value       = [for p in aws_ssm_parameter.api_keys : "aws ssm put-parameter --name ${p.name} --type SecureString --overwrite --value '<your key>'"]
}

output "run_now" {
  description = "Trigger a run without waiting for 07:00."
  value       = "aws lambda invoke --function-name ${aws_lambda_function.daily.function_name} --invocation-type Event /dev/null"
}
