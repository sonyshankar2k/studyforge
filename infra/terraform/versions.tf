terraform {
  # Works with OpenTofu (what CI uses) and Terraform.
  required_version = ">= 1.6"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = ">= 6.59, < 7.0"
    }
  }

  # Remote state, so a team shares one source of truth. Fill in and uncomment:
  # backend "s3" {
  #   bucket       = "my-terraform-state"
  #   key          = "studyforge/terraform.tfstate"
  #   region       = "us-east-1"
  #   use_lockfile = true
  # }
}

provider "aws" {
  region = var.region

  # Every resource gets these tags (cost reports, ownership, clean-up).
  default_tags {
    tags = local.tags
  }
}
