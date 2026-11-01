# ------------------------------------------------------------------ App role (IRSA)
# The API and worker pods use the Kubernetes service account "studyforge-api".
# EKS swaps its token for temporary AWS credentials for this role, so the app
# reads and writes protocols in S3 with no access keys in config or secrets.

locals {
  oidc_provider_arn = var.create_eks ? one(module.eks[*].oidc_provider_arn) : var.existing_oidc_provider_arn
  # "arn:aws:iam::123:oidc-provider/oidc.eks.../id/ABC" -> "oidc.eks.../id/ABC"
  oidc_provider_host = local.create_app_role ? element(split("oidc-provider/", local.oidc_provider_arn), 1) : ""
  create_app_role    = var.create_eks || var.existing_oidc_provider_arn != ""
}

data "aws_iam_policy_document" "app_storage" {
  statement {
    sid       = "ProtocolObjects"
    actions   = ["s3:GetObject", "s3:PutObject", "s3:DeleteObject"]
    resources = ["${aws_s3_bucket.uploads.arn}/protocols/*"]
  }
}

resource "aws_iam_policy" "app_storage" {
  name        = "${local.name}-app-storage"
  description = "StudyForge API/worker: read and write uploaded protocols only"
  policy      = data.aws_iam_policy_document.app_storage.json
}

data "aws_iam_policy_document" "app_trust" {
  count = local.create_app_role ? 1 : 0

  statement {
    actions = ["sts:AssumeRoleWithWebIdentity"]
    principals {
      type        = "Federated"
      identifiers = [local.oidc_provider_arn]
    }
    condition {
      test     = "StringEquals"
      variable = "${local.oidc_provider_host}:sub"
      values   = ["system:serviceaccount:${var.k8s_namespace}:studyforge-api"]
    }
    condition {
      test     = "StringEquals"
      variable = "${local.oidc_provider_host}:aud"
      values   = ["sts.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "app" {
  count              = local.create_app_role ? 1 : 0
  name               = "${local.name}-app"
  assume_role_policy = data.aws_iam_policy_document.app_trust[0].json
}

resource "aws_iam_role_policy_attachment" "app_storage" {
  count      = local.create_app_role ? 1 : 0
  role       = aws_iam_role.app[0].name
  policy_arn = aws_iam_policy.app_storage.arn
}

# ------------------------------------------------------------------ CI role (GitHub OIDC)
# GitHub Actions on the main branch of var.github_repository may push images to ECR.

locals {
  create_ci_role = var.github_repository != ""
}

resource "aws_iam_openid_connect_provider" "github" {
  count          = local.create_ci_role && var.create_github_oidc_provider ? 1 : 0
  url            = "https://token.actions.githubusercontent.com"
  client_id_list = ["sts.amazonaws.com"]
}

data "aws_iam_openid_connect_provider" "github" {
  count = local.create_ci_role && !var.create_github_oidc_provider ? 1 : 0
  url   = "https://token.actions.githubusercontent.com"
}

data "aws_iam_policy_document" "ci_trust" {
  count = local.create_ci_role ? 1 : 0

  statement {
    actions = ["sts:AssumeRoleWithWebIdentity"]
    principals {
      type = "Federated"
      identifiers = [coalesce(
        one(aws_iam_openid_connect_provider.github[*].arn),
        one(data.aws_iam_openid_connect_provider.github[*].arn),
      )]
    }
    condition {
      test     = "StringEquals"
      variable = "token.actions.githubusercontent.com:aud"
      values   = ["sts.amazonaws.com"]
    }
    condition {
      test     = "StringEquals"
      variable = "token.actions.githubusercontent.com:sub"
      values   = ["repo:${var.github_repository}:ref:refs/heads/main"]
    }
  }
}

data "aws_iam_policy_document" "ci_push" {
  statement {
    sid       = "Login"
    actions   = ["ecr:GetAuthorizationToken"]
    resources = ["*"]
  }
  statement {
    sid = "PushImages"
    actions = [
      "ecr:BatchCheckLayerAvailability",
      "ecr:BatchGetImage",
      "ecr:CompleteLayerUpload",
      "ecr:InitiateLayerUpload",
      "ecr:PutImage",
      "ecr:UploadLayerPart",
    ]
    resources = [for repo in aws_ecr_repository.app : repo.arn]
  }
}

resource "aws_iam_role" "ci" {
  count              = local.create_ci_role ? 1 : 0
  name               = "${local.name}-github-ci"
  assume_role_policy = data.aws_iam_policy_document.ci_trust[0].json
}

resource "aws_iam_role_policy" "ci_push" {
  count  = local.create_ci_role ? 1 : 0
  name   = "ecr-push"
  role   = aws_iam_role.ci[0].id
  policy = data.aws_iam_policy_document.ci_push.json
}
