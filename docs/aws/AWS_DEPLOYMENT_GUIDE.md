# AWS Deployment Guide

This document provides a step-by-step guide for deploying the MCaaS stack to AWS.

_This document is auto-generated and will be populated during the session._

---

## ⚠️ Critical: AWS Teardown Procedure

> **READ THIS BEFORE TEARING DOWN ANY AWS DEPLOYMENT.** Incorrect teardown order leaves orphaned AWS resources that continue to incur costs.

### Teardown is a Two-Step Process

**Never** run `deploy-aws.py --tear-down` alone. The correct procedure is:

#### Step 1 — Remove Kubernetes Resources (MUST BE DONE FIRST)

```bash
# Make sure kubectl points to the correct EKS cluster
kubectl config current-context

# Remove all MCaaS K8s resources (this triggers ALB/NLB/EBS cleanup)
python scripts/teardown.py --client aws
```

**Why first?** Kubernetes creates AWS resources (ALBs, NLBs, EBS volumes) on your behalf. Removing K8s resources first allows the cluster controllers to issue the corresponding AWS delete calls. If you destroy the cluster before this step, those delete calls never happen — leaving orphaned resources.

#### Step 2 — Destroy the EKS Cluster

```bash
# Only after Step 1 is complete
python scripts/deploy-aws.py --tear-down

# Or for a specific cluster
python scripts/deploy-aws.py --tear-down --cluster-name my-cluster --region us-west-2
```

#### Step 3 — Verify and Clean Up Orphaned Resources

After both steps, manually check for and remove:

| Orphaned Resource | How to Find | Cost If Left |
|-------------------|-------------|-------------|
| ALBs / NLBs | AWS Console → EC2 → Load Balancers, or `aws elbv2 describe-load-balancers` | ~$16–25/month each |
| EBS volumes | AWS Console → EC2 → Volumes, or `aws ec2 describe-volumes` | ~$0.08/GB/month |
| CloudWatch log groups | `aws logs describe-log-groups --log-group-name-prefix /aws/eks/` | Varies |
| Route53 / Cloudflare DNS records | Console → check CNAME records pointing to deleted LBs | N/A (but broken DNS) |
| ACM certificates | AWS Console → Certificate Manager | N/A (but cluttered) |

> **COST WARNING:** A single orphaned ALB costs ~$16–25/month. Always verify cleanup.

### Quick Verification After Teardown

```bash
# Check no MCaaS namespaces remain
kubectl get namespaces

# Check no Helm releases remain
helm list -A

# Check no PVCs remain (these map to EBS volumes)
kubectl get pvc -A

# Check no load balancers remain
kubectl get ingress -A
kubectl get svc -A | grep LoadBalancer

# Check for orphaned AWS resources
aws elbv2 describe-load-balancers --query 'LoadBalancers[].{Name:LoadBalancerName,Type:Type}' --output table
aws ec2 describe-volumes --query 'Volumes[].{ID:VolumeId,Size:Size,State:State}' --output table
```

---

For the full deployment and troubleshooting guide, see [docs/aws-deployment.md](docs/aws-deployment.md).
