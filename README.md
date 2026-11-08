# Job Radar

A serverless system on AWS that finds UK and worldwide-remote DevOps jobs every morning, keeps only new jobs a UK-based applicant can take, scores them against my CV, and emails me the best matches.

Infrastructure: Terraform, one apply, two regions (eu-west-2 for the pipeline, eu-west-1 for SES email receiving).

## Deploy

```bash
cd terraform
cp terraform.tfvars.example terraform.tfvars   # fill in your email
terraform init
terraform fmt -recursive && terraform validate
terraform plan -out=tfplan
terraform apply tfplan
terraform output
```

Then, once:
1. Add the DNS records from `terraform output cloudflare_dns_records` in Cloudflare (DNS only).
2. Click the two AWS confirmation emails (SES recipient, SNS alarms; three with the Ireland alarm topic).
3. Store the API keys with the commands in `terraform output set_api_keys`.
4. Point job alerts on LinkedIn, Indeed and others at `terraform output alert_address`.
