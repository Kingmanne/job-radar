terraform {
  required_version = ">= 1.10"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 6.0"
    }
    archive = {
      source  = "hashicorp/archive"
      version = "~> 2.7"
    }
  }

  # Same state bucket as the EKS project, separate key.
  backend "s3" {
    bucket       = "job-radar-tfstate-229173780431"
    key          = "job-radar/terraform.tfstate"
    region       = "eu-west-2"
    encrypt      = true
    use_lockfile = true
  }
}

# Everything runs in London...
provider "aws" {
  region = var.region
  default_tags {
    tags = { Project = "job-radar", ManagedBy = "terraform" }
  }
}

# ...except SES email receiving, which London doesn't offer.
provider "aws" {
  alias  = "ireland"
  region = var.receiving_region
  default_tags {
    tags = { Project = "job-radar", ManagedBy = "terraform" }
  }
}
