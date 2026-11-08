# One-time setup, applied from your Mac: the roles GitHub Actions uses.
# Kept out of the main stack so a pipeline run can never edit its own access.
#
#   cd bootstrap && terraform init && terraform apply
#
# Then put the two output ARNs in the repo as Actions variables.

terraform {
  required_version = ">= 1.10"
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 6.0"
    }
  }
  backend "s3" {
    bucket       = "eks-platform-tfstate-371510064293"
    key          = "job-radar/bootstrap.tfstate"
    region       = "eu-west-2"
    encrypt      = true
    use_lockfile = true
  }
}

provider "aws" {
  region = "eu-west-2"
  default_tags {
    tags = { Project = "job-radar", ManagedBy = "terraform", Stack = "bootstrap" }
  }
}

variable "github_repo" {
  type    = string
  default = "Kingmanne/job-radar"
}

variable "state_bucket" {
  type    = string
  default = "eks-platform-tfstate-371510064293"
}

variable "create_oidc_provider" {
  description = "An AWS account can hold only one GitHub OIDC provider. The EKS project probably made it already: leave false to reuse it."
  type        = bool
  default     = false
}

data "aws_caller_identity" "current" {}

locals {
  account = data.aws_caller_identity.current.account_id
  oidc_arn = (var.create_oidc_provider
    ? aws_iam_openid_connect_provider.github[0].arn
  : data.aws_iam_openid_connect_provider.github[0].arn)
  # Everything the app stack creates is named job-radar-*. The CI roles are
  # named gha-job-radar-* on purpose, so the apply role cannot edit them.
  app = "job-radar"
}

data "aws_iam_openid_connect_provider" "github" {
  count = var.create_oidc_provider ? 0 : 1
  url   = "https://token.actions.githubusercontent.com"
}

resource "aws_iam_openid_connect_provider" "github" {
  count          = var.create_oidc_provider ? 1 : 0
  url            = "https://token.actions.githubusercontent.com"
  client_id_list = ["sts.amazonaws.com"]
}

# ---------- plan role: pull requests, read-only ----------

resource "aws_iam_role" "plan" {
  name                 = "gha-job-radar-plan"
  max_session_duration = 3600
  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { Federated = local.oidc_arn }
      Action    = "sts:AssumeRoleWithWebIdentity"
      Condition = {
        StringEquals = {
          "token.actions.githubusercontent.com:aud" = "sts.amazonaws.com"
          "token.actions.githubusercontent.com:sub" = "repo:${var.github_repo}:pull_request"
        }
      }
    }]
  })
}

resource "aws_iam_role_policy_attachment" "plan_readonly" {
  role       = aws_iam_role.plan.name
  policy_arn = "arn:aws:iam::aws:policy/ReadOnlyAccess"
}

resource "aws_iam_role_policy" "plan_extra" {
  name = "state-and-ssm"
  role = aws_iam_role.plan.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid       = "ReadSecureStringsDuringRefresh"
        Effect    = "Allow"
        Action    = "kms:Decrypt"
        Resource  = "*"
        Condition = { StringEquals = { "kms:ViaService" = "ssm.eu-west-2.amazonaws.com" } }
      }
    ]
  })
}

# ---------- apply role: main branch only, scoped to job-radar-* ----------

resource "aws_iam_role" "apply" {
  name                 = "gha-job-radar-apply"
  max_session_duration = 3600
  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { Federated = local.oidc_arn }
      Action    = "sts:AssumeRoleWithWebIdentity"
      Condition = {
        StringEquals = {
          "token.actions.githubusercontent.com:aud" = "sts.amazonaws.com"
          "token.actions.githubusercontent.com:sub" = "repo:${var.github_repo}:ref:refs/heads/main"
        }
      }
    }]
  })
}

resource "aws_iam_role_policy" "apply" {
  name = "manage-job-radar"
  role = aws_iam_role.apply.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid    = "TerraformState"
        Effect = "Allow"
        Action = ["s3:GetObject", "s3:PutObject", "s3:DeleteObject"]
        Resource = [
          "arn:aws:s3:::${var.state_bucket}/job-radar/terraform.tfstate",
          "arn:aws:s3:::${var.state_bucket}/job-radar/terraform.tfstate.tflock",
        ]
      },
      {
        Sid       = "TerraformStateList"
        Effect    = "Allow"
        Action    = "s3:ListBucket"
        Resource  = "arn:aws:s3:::${var.state_bucket}"
        Condition = { StringLike = { "s3:prefix" = ["job-radar/*"] } }
      },
      {
        Sid    = "AppRoles"
        Effect = "Allow"
        Action = [
          "iam:GetRole", "iam:CreateRole", "iam:DeleteRole", "iam:UpdateRole", "iam:UpdateAssumeRolePolicy",
          "iam:TagRole", "iam:UntagRole", "iam:ListRoleTags",
          "iam:GetRolePolicy", "iam:PutRolePolicy", "iam:DeleteRolePolicy", "iam:ListRolePolicies",
          "iam:ListAttachedRolePolicies", "iam:AttachRolePolicy", "iam:DetachRolePolicy",
          "iam:ListInstanceProfilesForRole", "iam:PassRole",
        ]
        Resource = "arn:aws:iam::${local.account}:role/${local.app}-*"
      },
      {
        Sid    = "AppResources"
        Effect = "Allow"
        Action = ["lambda:*", "dynamodb:*", "sqs:*", "sns:*", "logs:*", "cloudwatch:*", "scheduler:*", "s3:*"]
        Resource = [
          "arn:aws:lambda:*:${local.account}:function:${local.app}-*",
          "arn:aws:dynamodb:*:${local.account}:table/${local.app}-*",
          "arn:aws:sqs:*:${local.account}:${local.app}-*",
          "arn:aws:sns:*:${local.account}:${local.app}-*",
          "arn:aws:logs:*:${local.account}:log-group:/aws/lambda/${local.app}-*",
          "arn:aws:cloudwatch:*:${local.account}:alarm:${local.app}-*",
          "arn:aws:scheduler:*:${local.account}:schedule/default/${local.app}-*",
          "arn:aws:s3:::${local.app}-inbox-*",
        ]
      },
      {
        Sid      = "AppParameters"
        Effect   = "Allow"
        Action   = "ssm:*"
        Resource = "arn:aws:ssm:*:${local.account}:parameter/${local.app}/*"
      },
      {
        Sid       = "DecryptParameters"
        Effect    = "Allow"
        Action    = "kms:Decrypt"
        Resource  = "*"
        Condition = { StringEquals = { "kms:ViaService" = "ssm.eu-west-2.amazonaws.com" } }
      },
      {
        # SES identities, receipt rules and these list/describe calls have no
        # resource-level permissions, so they need "*".
        Sid    = "NoResourceLevel"
        Effect = "Allow"
        Action = [
          "ses:*", "ssm:DescribeParameters", "logs:DescribeLogGroups", "cloudwatch:DescribeAlarms",
          "scheduler:ListSchedules", "lambda:ListFunctions", "sns:ListTopics", "sqs:ListQueues",
          "dynamodb:ListTables", "iam:ListRoles", "s3:ListAllMyBuckets",
        ]
        Resource = "*"
      },
    ]
  })
}

output "plan_role_arn" {
  value = aws_iam_role.plan.arn
}

output "apply_role_arn" {
  value = aws_iam_role.apply.arn
}
