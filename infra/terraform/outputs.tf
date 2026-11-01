output "uploads_bucket" {
  description = "Set as S3_BUCKET in the app config (k8s/base/configmap.yaml)."
  value       = aws_s3_bucket.uploads.bucket
}

output "ecr_repositories" {
  description = "Image repositories for the api and web images."
  value       = { for k, repo in aws_ecr_repository.app : k => repo.repository_url }
}

output "app_role_arn" {
  description = "Annotate the studyforge-api service account with this (eks.amazonaws.com/role-arn)."
  value       = one(aws_iam_role.app[*].arn)
}

output "ci_role_arn" {
  description = "Set as the AWS_ROLE_ARN repository variable for the deploy workflow."
  value       = one(aws_iam_role.ci[*].arn)
}

output "eks_cluster_name" {
  description = "aws eks update-kubeconfig --name <this>"
  value       = one(module.eks[*].cluster_name)
}
