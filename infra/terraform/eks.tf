# ------------------------------------------------------------------ Optional: VPC + EKS
# terraform apply -var create_eks=true
# Costs money while it runs (control plane + nodes + NAT gateway). Destroy when done.

data "aws_availability_zones" "available" {
  count = var.create_eks ? 1 : 0
  state = "available"
}

module "vpc" {
  source  = "terraform-aws-modules/vpc/aws"
  version = "~> 6.7"
  count   = var.create_eks ? 1 : 0

  name            = local.name
  cidr            = "10.40.0.0/16"
  azs             = slice(data.aws_availability_zones.available[0].names, 0, 3)
  private_subnets = ["10.40.0.0/20", "10.40.16.0/20", "10.40.32.0/20"]
  public_subnets  = ["10.40.240.0/24", "10.40.241.0/24", "10.40.242.0/24"]

  enable_nat_gateway = true
  single_nat_gateway = var.environment != "prod" # one NAT is cheaper; prod gets one per AZ

  # Lets the AWS Load Balancer Controller find the right subnets for the Ingress.
  public_subnet_tags  = { "kubernetes.io/role/elb" = 1 }
  private_subnet_tags = { "kubernetes.io/role/internal-elb" = 1 }
}

module "eks" {
  source  = "terraform-aws-modules/eks/aws"
  version = "~> 21.29"
  count   = var.create_eks ? 1 : 0

  name               = local.name
  kubernetes_version = var.kubernetes_version

  vpc_id     = module.vpc[0].vpc_id
  subnet_ids = module.vpc[0].private_subnets

  endpoint_public_access                   = true
  enable_cluster_creator_admin_permissions = true
  enable_irsa                              = true

  addons = {
    coredns    = {}
    kube-proxy = {}
    vpc-cni    = { before_compute = true }
  }

  eks_managed_node_groups = {
    default = {
      ami_type       = "AL2023_x86_64_STANDARD"
      instance_types = ["t3.medium"]
      min_size       = 2
      max_size       = 4
      desired_size   = 2
    }
  }
}
