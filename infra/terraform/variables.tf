variable "project" {
  description = "Prefix for resource names."
  type        = string
  default     = "studyforge"
}

variable "environment" {
  description = "dev, staging or prod."
  type        = string
  default     = "dev"

  validation {
    condition     = contains(["dev", "staging", "prod"], var.environment)
    error_message = "environment must be dev, staging or prod."
  }
}

variable "region" {
  description = "AWS region."
  type        = string
  default     = "us-east-1"
}

variable "upload_retention_days" {
  description = "Days to keep old (overwritten or deleted) versions of uploaded protocols."
  type        = number
  default     = 90
}

variable "create_eks" {
  description = "Create a VPC and an EKS cluster. Off by default: EKS costs money every hour."
  type        = bool
  default     = false
}

variable "kubernetes_version" {
  description = "EKS Kubernetes version (when create_eks = true)."
  type        = string
  default     = "1.34"
}

variable "existing_oidc_provider_arn" {
  description = "Bring your own cluster: its IAM OIDC provider ARN, so pods can use the app's IAM role (IRSA). Ignored when create_eks = true."
  type        = string
  default     = ""
}

variable "k8s_namespace" {
  description = "Kubernetes namespace the app runs in (must match k8s/)."
  type        = string
  default     = "studyforge"
}

variable "github_repository" {
  description = "owner/repo allowed to push images to ECR from GitHub Actions (OIDC, no stored keys). Empty = no deploy role."
  type        = string
  default     = ""
}

variable "create_github_oidc_provider" {
  description = "Create the GitHub Actions OIDC provider. Set false if the AWS account already has one."
  type        = bool
  default     = true
}
