# AWS/EKS Deployment Guide

This guide covers deploying MCaaS to AWS using a full Infrastructure-as-Code approach with EKS, EBS, ALB, and cert-manager.

## Architecture Overview

| Component        | AWS Service              | Details                                      |
|------------------|--------------------------|----------------------------------------------|
| Kubernetes       | EKS                      | Managed node groups (m5.xlarge, m5.2xlarge) |
| Storage          | EBS (gp3/io1)            | CSI driver via EBS CSI addon                 |
| Ingress          | ALB (AWS Load Balancer)  | ALB Ingress Controller via Helm               |
| TLS Certificates | cert-manager + Let's Encrypt | HTTP01 or DNS01 (Cloudflare) challenge    |
| DNS              | Cloudflare (recommended) | For automatic DNS & wildcard certificates    |

## Prerequisites

### Required Tools

Install these CLI tools before deploying:

| Tool      | Version  | Install                                              |
|-----------|----------|------------------------------------------------------|
| `aws`     | ≥ 2.x    | `pip install awscli` or [AWS CLI installer](https://docs.aws.amazon.com/cli/latest/userguide/getting-started-install.html) |
| `eksctl`  | ≥ 0.170  | [eksctl.io](https://eksctl.io/)                      |
| `kubectl` | ≥ 1.27   | [kubernetes.io](https://kubernetes.io/docs/tasks/tools/) |
| `helm`    | ≥ 3.12   | [helm.sh](https://helm.sh/docs/intro/install/)       |
| `git`     | ≥ 2.x    | System package manager                                |
| `openssl` | Any      | System package manager                                |
| `python`  | ≥ 3.9    | [python.org](https://www.python.org/)                |

### AWS Credentials

Configure AWS credentials before starting:

```bash
# Option 1: AWS CLI configuration
aws configure

# Option 2: Environment variables
export AWS_ACCESS_KEY_ID="your-access-key"
export AWS_SECRET_ACCESS_KEY="your-secret-key"
export AWS_DEFAULT_REGION="us-east-1"

# Option 3: IAM role (if running on EC2)
# Use instance profile with appropriate permissions
```

### Required IAM Permissions

The AWS user/role needs at minimum:
- `eksctl` permissions (EKS full access, VPC, IAM)
- EC2 permissions (for node groups)
- Elastic Load Balancing permissions
- EBS CSI driver permissions

## Quick Start

### 1. Deploy Everything (Infrastructure + Applications)

```bash
python deploy-aws.py
```

This will:
1. Create the EKS cluster using eksctl
2. Install EBS CSI driver and AWS Load Balancer Controller
3. Install cert-manager
4. Apply StorageClasses and Namespaces
5. Deploy all MCaaS services (PostgreSQL, OpenSearch, Shuffle, Zammad, Wazuh, CISO Assistant)

### 2. Deploy with Custom Client Config

```bash
python deploy-aws.py --client aws
```

### 3. Deploy with Cloudflare DNS01 (Wildcard Certificates)

Enable Cloudflare DNS01 challenges for wildcard TLS certificates:

```bash
python deploy-aws.py --cloudflare-token <YOUR_CLOUDFLARE_API_TOKEN>
```

This automatically creates the `cloudflare-api-token-secret` in the `cert-manager` namespace
and applies the `letsencrypt-cloudflare` ClusterIssuer. See [Cloudflare DNS01 Setup](#cloudflare-dns01-setup) for details.

### 4. Skip Infrastructure (Use Existing EKS Cluster)

If you already have an EKS cluster:

```bash
python deploy-aws.py --skip-cluster
```

### 5. Skip Infrastructure Setup (Use Existing Add-ons)

If add-ons are already installed but you want to deploy applications:

```bash
python deploy-aws.py --skip-infrastructure
```

### 6. Dry Run

Preview all changes without executing:

```bash
python deploy-aws.py --dry-run
```

## Configuration

### Client Configuration

Edit `clients/aws/config.yaml` to customize:

```yaml
client:
  name: aws
  prefix: mcaas
  domain: testcustomer.socom.co.il  # Your Cloudflare domain
  database_name: mcaas_db
  namespaces:
    managed-it: managed-it
    security-ops: security-ops
    grc: grc
    wazuh: wazuh
  ingress:
    zammad_host: zammad.testcustomer.socom.co.il
    ciso_host: ciso.testcustomer.socom.co.il
  aws:
    cluster_name: mcaas-eks
    region: eu-west-1
```

### Cluster Configuration

Edit `aws/eksctl-cluster.yaml` to customize:
- Node group instance types and sizes
- VPC CIDR ranges
- Availability zones
- IAM role configurations

### Environment Variables

Create a `.env` file or set environment variables:

```bash
# Optional: Override default passwords
POSTGRESQL_PASSWORD=your-secure-password
OPENSEARCH_PASSWORD=your-secure-password
SHUFFLE_API_KEY=your-api-key
ZAMMAD_SECRET=your-secret
CISO_DJANGO_SECRET=your-django-secret
```

## Deployment Phases

### Phase 1: Infrastructure

1. **EKS Cluster** — Created via `eksctl create cluster`
2. **EBS CSI Driver** — EKS addon for persistent volume provisioning
3. **AWS Load Balancer Controller** — Helm chart from eks-charts
4. **cert-manager** — Helm chart with CRDs for TLS certificate management
5. **StorageClasses** — `gp3` (default), `io1` (high-perf), `wazuh-storage`
6. **Namespaces** — `managed-it`, `security-ops`, `grc`, `wazuh`

### Phase 2: Applications

1. **PostgreSQL** — Bitnami Helm chart with gp3 storage
2. **OpenSearch** — Helm chart with gp3 storage and security plugin
3. **Shuffle SOAR** — OCI Helm chart with external OpenSearch
4. **Zammad** — OCI Helm chart with ALB ingress and cert-manager TLS
5. **CISO Assistant** — OCI Helm chart with ALB ingress and cert-manager TLS
6. **Wazuh** — Kustomize deployment with gp3 storage for wazuh-storage class

## DNS and TLS Setup

### Option 1: Cloudflare DNS01 (Recommended for Production & Wildcards)

Cloudflare DNS01 challenges support **wildcard certificates** (`*.testcustomer.socom.co.il`),
which HTTP01 cannot issue. This is the recommended approach for Cloudflare-managed domains.

#### Cloudflare DNS01 Setup

**Step 1 — Create a Cloudflare API Token**

1. Go to [Cloudflare Dashboard](https://dash.cloudflare.com/profile/api-tokens)
2. Click **Create Token** → Use the **Edit zone DNS** template
3. Under **Permissions**, set:
   - Zone → DNS → Edit
4. Under **Zone Resources**, set:
   - Include → Specific zone → `socom.co.il`
5. Copy the generated token

**Step 2 — Deploy with `--cloudflare-token`**

```bash
python deploy-aws.py --cloudflare-token <YOUR_CLOUDFLARE_API_TOKEN>
```

This automatically:
- Creates the `cloudflare-api-token-secret` Kubernetes secret in the `cert-manager` namespace
- Waits for cert-manager-webhook to be ready
- Applies the `letsencrypt-cloudflare` ClusterIssuer

**Step 3 — Create DNS Records in Cloudflare**

After deployment, retrieve the ALB endpoint:

```bash
kubectl get ingress -A
```

Then in the Cloudflare Dashboard, create DNS records for `testcustomer.socom.co.il`:

| Type  | Name                          | Content                        | Proxy |
|-------|-------------------------------|--------------------------------|-------|
| CNAME | `*.testcustomer`              | `<ALB-hostname>`               | DNS only (grey cloud) |
| CNAME | `testcustomer`                | `<ALB-hostname>`               | DNS only (grey cloud) |

> **Note:** DNS proxy (orange cloud) must be **disabled** for ACME DNS01 challenges to work.

**Step 4 — Use the Cloudflare Issuer in Ingress**

Annotate your Ingress resources with:

```yaml
cert-manager.io/cluster-issuer: letsencrypt-cloudflare
```

#### Manual Cloudflare Secret Creation (Alternative)

If you prefer to create the secret manually instead of using `--cloudflare-token`:

```bash
kubectl create secret generic cloudflare-api-token-secret \
  --namespace cert-manager \
  --from-literal=api-token=<YOUR_CLOUDFLARE_API_TOKEN>

# Then apply the Cloudflare ClusterIssuer from ingress-and-cert.yaml
kubectl apply -f aws/ingress-and-cert.yaml
```

### Option 2: HTTP01 Challenge (Simpler, Default)

The default configuration uses HTTP01 challenge, which works out of the box
with the ALB Ingress Controller. No additional DNS configuration required
beyond pointing your domain to the ALB.

> **Limitation:** HTTP01 does **not** support wildcard certificates. Use Cloudflare
> DNS01 (Option 1) if you need `*.testcustomer.socom.co.il`.

Annotate your Ingress resources with:

```yaml
cert-manager.io/cluster-issuer: letsencrypt-prod
```

## Accessing Services

After deployment, retrieve access information:

```bash
# Get the ALB endpoint
kubectl get ingress -A

# Get admin credentials
python deploy-aws.py --dry-run  # Review generated summary

# Or check the generated summary file
cat mcaas-aws-environment-summary.md
```

### Service URLs

With the default `testcustomer.socom.co.il` domain:

| Service          | URL                                      | Access     |
|------------------|------------------------------------------|------------|
| Zammad           | `https://zammad.testcustomer.socom.co.il` | ALB ingress |
| CISO Assistant   | `https://ciso.testcustomer.socom.co.il`   | ALB ingress |
| Wazuh Dashboard  | `https://wazuh.testcustomer.socom.co.il`  | ALB ingress  |
| Shuffle          | `https://shuffle.testcustomer.socom.co.il`| ALB ingress |

> **Note**: Wazuh uses an ALB ingress with ACM certificate for proper TLS termination.

### Wazuh NLB Configuration

After deploying Wazuh, configure the NLB scheme annotations. By default, all Wazuh NLBs
are created as `internal`, making them inaccessible from the internet.

**Apply the correct annotations** (bash or PowerShell):

```bash
# Bash
bash scripts/wazuh-nlb-annotations.sh

# PowerShell
.\scripts\wazuh-nlb-annotations.ps1
```

**Or manually:**

```bash
# Internet-facing (dashboard and manager)
kubectl annotate svc dashboard -n wazuh service.beta.kubernetes.io/aws-load-balancer-scheme=internet-facing --overwrite
kubectl annotate svc wazuh -n wazuh service.beta.kubernetes.io/aws-load-balancer-scheme=internet-facing --overwrite

# Internal-only (indexer and workers)
kubectl annotate svc indexer -n wazuh service.beta.kubernetes.io/aws-load-balancer-scheme=internal --overwrite
kubectl annotate svc wazuh-workers -n wazuh service.beta.kubernetes.io/aws-load-balancer-scheme=internal --overwrite
```

> **Important**: After changing scheme annotations, the AWS LB Controller deletes the old NLB
> and creates a new one with a different DNS name. Allow 60-120 seconds for provisioning.
>
> **Do NOT use** the legacy `service.beta.kubernetes.io/aws-load-balancer-internal: 0.0.0.0/0`
> annotation — it conflicts with the `scheme` annotation and causes reconciliation errors.

### Cloudflare DNS Records

Create CNAME records in Cloudflare (set to **DNS only**, not proxied):

| Record  | Type  | Target                                                          |
|---------|-------|-----------------------------------------------------------------|
| shuffle | CNAME | `<shuffle-alb-dns>` (from `kubectl get ingress -n security-ops`) |
| zammad  | CNAME | `<zammad-alb-dns>` (from `kubectl get ingress -n managed-it`)    |
| ciso    | CNAME | `<ciso-alb-dns>` (from `kubectl get ingress -n grc`)             |
| wazuh   | CNAME | `<wazuh-nlb-dns>` (from `kubectl get svc dashboard -n wazuh`)    |

> **Critical**: Wazuh CNAME records MUST be set to "DNS only" (grey cloud) in Cloudflare.
> Cloudflare proxy mode is incompatible with AWS NLBs (Layer 4 TCP).

## Teardown

> **⚠️ CRITICAL: Teardown is a two-step process.** Skipping Step 1 will leave orphaned AWS resources that continue to incur costs.

### Why Two Steps?

Kubernetes creates AWS resources on your behalf — ALBs, NLBs, EBS volumes — that are **not** managed by `eksctl`. If you delete the EKS cluster first (Step 2) without removing K8s resources (Step 1), Kubernetes never gets a chance to issue the delete calls that trigger cleanup of these AWS resources. This leaves **orphaned load balancers, EBS volumes, and other resources** that will continue to incur charges on your AWS account.

### Step 1 — Remove Kubernetes Resources (REQUIRED FIRST)

This removes all MCaaS Helm releases, K8s resources, PVCs, secrets, and namespaces. Critically, it also triggers Kubernetes to delete the associated AWS load balancers and release EBS volumes.

```bash
# Default (mcaas) deployment
python teardown.py

# Client-specific deployment
python teardown.py --client aws

# Skip PVC deletion if you want to preserve data
python teardown.py --client aws --skip-pvcs

# Skip namespace deletion (useful for shared clusters)
python teardown.py --client aws --skip-namespaces
```

> **Note:** `teardown.py` is **not** AWS-specific — it works against any Kubernetes cluster your `kubectl` context points to. Make sure your kubeconfig is pointing to the correct EKS cluster before running it.

**Verify all resources are removed:**

```bash
# Confirm no MCaaS namespaces remain
kubectl get namespaces

# Confirm no Helm releases remain
helm list -A

# Confirm no PVCs remain (these map to EBS volumes)
kubectl get pvc -A

# Confirm no load balancers remain
kubectl get ingress -A
kubectl get svc -A | grep LoadBalancer
```

### Step 2 — Destroy the EKS Cluster

Only after confirming Step 1 is complete:

```bash
# Delete default cluster (mcaas-eks in eu-west-1)
python deploy-aws.py --tear-down

# Delete a specific cluster
python deploy-aws.py --tear-down --cluster-name my-cluster --region us-west-2
```

This runs `eksctl delete cluster`, which removes:
- EKS control plane
- Worker node groups (EC2 instances)
- VPC, subnets, security groups (created by eksctl)
- IAM roles and policies (created by eksctl)
- CloudFormation stacks

### Post-Teardown AWS Cleanup

`eksctl delete cluster` and `teardown.py` do **not** clean up everything. After both steps, **manually verify and remove** the following orphaned resources:

| Resource | How to Check | How to Remove |
|----------|-------------|---------------|
| **Orphaned ALBs/NLBs** | `aws elbv2 describe-load-balancers` or AWS Console → EC2 → Load Balancers | `aws elbv2 delete-load-balancer --load-balancer-arn <arn>` |
| **Orphaned EBS volumes** | `aws ec2 describe-volumes --filters Name=tag:kubernetes.io/created-for/pv/name,Values=*` or AWS Console → EC2 → Volumes | `aws ec2 delete-volume --volume-id <id>` |
| **Route53 DNS records** | Route53 Console → Hosted zones | Remove CNAME/A records pointing to deleted ALB/NLB |
| **Cloudflare DNS records** | Cloudflare Dashboard | Remove CNAME records for `zammad`, `ciso`, `shuffle`, `wazuh` subdomains |
| **CloudWatch log groups** | `aws logs describe-log-groups --log-group-name-prefix /aws/eks/` | `aws logs delete-log-group --log-group-name <name>` |
| **ACM certificates** | AWS Console → Certificate Manager | Remove if no longer needed |
| **S3 buckets** (if any) | `aws s3 ls` | Remove any buckets created for the cluster |

> **⚠️ COST WARNING:** Orphaned load balancers cost ~$16–$25/month EACH. Orphaned EBS volumes cost ~$0.08/GB/month. Always verify cleanup after teardown.

### Quick Cleanup Script

To check for common orphaned resources after teardown:

```bash
# Check for remaining ALBs/NLBs
echo "=== Load Balancers ==="
aws elbv2 describe-load-balancers --query 'LoadBalancers[?VpcId==`<your-vpc-id>`].{Name:LoadBalancerName,Type:Type,ARN:LoadBalancerArn}' --output table

# Check for remaining EBS volumes
echo "=== EBS Volumes ==="
aws ec2 describe-volumes --filters Name=tag:kubernetes.io/created-for/pv/name,Values='*' --query 'Volumes[].{ID:VolumeId,Size:Size,State:State}' --output table

# Check for remaining CloudWatch log groups
echo "=== CloudWatch Log Groups ==="
aws logs describe-log-groups --log-group-name-prefix "/aws/eks/mcaas-eks" --query 'logGroups[].logGroupName' --output table
```

### Teardown for Non-AWS (Local) Clusters

For k3s, Rancher Desktop, or other local clusters, only Step 1 is needed:

```bash
# Default deployment
python teardown.py

# Client-specific deployment
python teardown.py --client demo
```

No Step 2 is needed because there's no cloud infrastructure to destroy.

## Troubleshooting

### EKS Cluster Creation Fails

```bash
# Check CloudFormation stack events
aws cloudformation describe-stack-events --stack-name eksctl-mcaas-eks-cluster

# View eksctl logs
eksctl utils describe-stacks --cluster mcaas-eks --region us-east-1
```

### Pods Stuck in Pending

```bash
# Check node capacity
kubectl get nodes -o wide
kubectl describe node <node-name>

# Check EBS CSI driver
kubectl get pods -n kube-system -l app.kubernetes.io/name=aws-ebs-csi-driver

# Check StorageClass
kubectl get storageclass
```

### ALB Not Created

```bash
# Check AWS Load Balancer Controller
kubectl get pods -n kube-system -l app.kubernetes.io/name=aws-load-balancer-controller

# Check controller logs
kubectl logs -n kube-system -l app.kubernetes.io/name=aws-load-balancer-controller

# Verify IAM service account
kubectl get sa -n kube-system aws-load-balancer-controller
```

### Certificate Issuance Fails

```bash
# Check cert-manager
kubectl get pods -n cert-manager
kubectl get certificaterequest -A

# Check certificate details
kubectl describe certificate -A

# Check ACME challenge
kubectl get challenges -A
```

### Storage Issues

```bash
# Check EBS volumes
aws ec2 describe-volumes --filters Name=tag:kubernetes.io/created-for/pv/name,Values=*

# Check PVC status
kubectl get pvc -A
```

## Cost Estimates

| Resource                | Type        | Count | Est. Monthly Cost |
|-------------------------|-------------|-------|-------------------|
| EKS Control Plane      | -           | 1     | ~$73              |
| Worker Nodes (m5.xlarge)| On-Demand   | 4     | ~$560             |
| Monitoring Nodes (m5.2xlarge) | On-Demand | 2 | ~$560          |
| EBS Volumes (gp3)       | 20-30 Gi each | 5+ | ~$15            |
| NAT Gateway             | -           | 3     | ~$90              |
| ALB                     | -           | 1     | ~$30              |
| **Total (estimated)**   |             |       | **~$1,328/mo**   |

> Consider Reserved Instances or Savings Plans for production to reduce compute costs by 30-50%.

## File Structure

```
aws/
├── eksctl-cluster.yaml        # EKS cluster definition
├── storage-classes.yaml       # EBS StorageClasses (gp3, io1, wazuh)
├── ingress-and-cert.yaml      # ALB IngressClass + cert-manager issuers
└── namespaces.yaml            # Kubernetes namespaces

clients/aws/
├── config.yaml                # AWS client configuration
└── values/
    ├── postgresql.yaml         # PostgreSQL Helm values (gp3 storage)
    ├── opensearch.yaml         # OpenSearch Helm values (gp3 storage)
    ├── shuffle.yaml            # Shuffle Helm values (gp3 storage)
    ├── zammad.yaml             # Zammad Helm values (ALB ingress)
    └── ciso-assistant.yaml     # CISO Assistant Helm values (ALB ingress)

scripts/
├── deploy-aws.sh               # Bash wrapper script
└── deploy-aws.ps1              # PowerShell wrapper script
```