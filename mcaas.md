Skyddex MCaaS Infrastructure Manifests
Technical Site Lead: Daniel Beard
Target Framework: veloctrl IaC Integration

Strategic Overview: This document centralizes the Helm values.yaml configurations and core resource
manifests required for the Sovereign Managed Compliance as a Service (MCaaS) stack. These definitions are
structured to support automated compute provisioning through the veloctrl self-service portal, ensuring
strict multi-tenant separation for Specialized Cybersecurity and Managed IT Services.

1. Core Infrastructure & Namespaces
Logical separation boundaries for the Kubernetes cluster.
apiVersion: v1
kind: Namespace
metadata:
name: security-ops
---
apiVersion: v1
kind: Namespace
metadata:
name: managed-it
---
apiVersion: v1
kind: Namespace
metadata:
name: grc

2. Foundational Data Services
PostgreSQL Database (values.yaml)
Target Namespace: managed-it. Externalized backend preventing bundled schema
validation errors.
global:
postgresql:
auth:
    # Use existing secret for passwords
    existingSecret: "mcaas-postgresql-secret"
    secretKeys:
      postgresPasswordKey: "postgres-password"
database: "mcaas_db"
  primary:
    persistence:
      enabled: true
      size: 10Gi

OpenSearch Indexer (values.yaml)
Target Namespace: security-ops. Data backend for SIEM and SOAR.
singleNode: true
extraEnvs:
- name: OPENSEARCH_INITIAL_ADMIN_PASSWORD
  valueFrom:
    secretKeyRef:
      name: "mcaas-opensearch-secret"
      key: "opensearch-password"
persistence:
enabled: true
size: 20Gi

3. Specialized Cybersecurity
Wazuh SIEM & XDR (values.yaml)
Target Namespace: security-ops. Includes the patched certs-generator image
configuration to bypass registry deprecation.
wazuh:
manager:
enabled: true
dashboard:
enabled: true
indexer:
enabled: false
external:
host: "mcaas-opensearch.security-ops.svc.cluster.local"
port: 9200
  # Use existing secret for the password
  secret:
    name: "mcaas-opensearch-secret"
    key: "opensearch-password"
certsGenerator:
image:
registry: "docker.io"
repository: "bitnami/kubectl"
tag: "1.28.4" # Use a specific, recent, and stable version instead of 'latest'

Shuffle SOAR (values.yaml)
Target Namespace: security-ops. Automated incident response workflow engine.

backend:
opensearch:
host: "mcaas-opensearch.security-ops.svc.cluster.local"
port: 9200
  # Use existing secret for the password
  secret:
    name: "mcaas-opensearch-secret"
    key: "opensearch-password"
orborus:
enabled: true
persistence:
enabled: true
size: 10Gi

4. Managed IT Services & GRC

Zammad Helpdesk (values.yaml)
Target Namespace: managed-it. Multi-tenant support application.

zammadConfig:
  postgresql:
    enabled: false
    host: "mcaas-postgresql.managed-it.svc.cluster.local"
    port: 5432
    user: "postgres"
    pass: ""  # Password comes from secrets.postgresql existing secret
    db: "zammad"
  elasticsearch:
    enabled: false
    initialisation: false  # Skip elasticsearch-init container since ES is disabled
  redis:
    enabled: true
    host: "mcaas-zammad-redis"
    port: 6379
    pass: "zammad"

# Use existing secrets for PostgreSQL and Redis
secrets:
  postgresql:
    useExisting: true
    secretName: "mcaas-postgresql-secret"
    secretKey: "postgres-password"
  redis:
    useExisting: true
    secretName: "mcaas-zammad-redis-pass"
    secretKey: "redis-password"

# Disable the Bitnami sub-charts
postgresql:
  enabled: false
elasticsearch:
  enabled: false

# Configure the Bitnami Redis sub-chart to use our existing secret
redis:
  auth:
    existingSecret: "mcaas-zammad-redis-pass"
    existingSecretPasswordKey: "redis-password"

# Enable Ingress to expose the Zammad UI externally
ingress:
  enabled: true
  className: "nginx"
  hosts:
    - host: zammad.mcaas.example.com
      paths:
        - path: /
          pathType: ImplementationSpecific

CISO Assistant (values.yaml)
Target Namespace: grc. Framework mapping and compliance tracking.

postgresql:
  enabled: false
global:
  domain: ciso.mcaas.example.com
backend:
  config:
    databaseType: externalPgsql
    djangoSecretKey: "<generated-secret-key>"
externalPgsql:
  host: "mcaas-postgresql.managed-it.svc.cluster.local"
  port: 5432
  user: "postgres"
  existingSecret: "mcaas-postgresql-secret"
  database: "ciso-assistant"
ingress:
  enabled: true