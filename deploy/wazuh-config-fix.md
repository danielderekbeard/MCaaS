# Wazuh ConfigMap Fix for Deployment

## Problem
Wazuh StatefulSets reference ConfigMaps with kustomize hash suffixes (e.g., `indexer-conf-46b5244fc2`).
When these are deleted, the pods fail to start with:
```
configmap "indexer-conf-46b5244fc2" not found
```

## Solution

### Option 1: Create Hashed ConfigMaps (Quick Fix)
After deploying Wazuh, check what hashed ConfigMap names the pods expect:
```bash
kubectl describe pod wazuh-indexer-0 -n wazuh | grep "Name:.*indexer-conf"
kubectl describe pod wazuh-manager-master-0 -n wazuh | grep "Name:.*wazuh-conf"
```

Then create ConfigMaps with those exact names.

### Option 2: Recreate StatefulSets with Non-Hashed Names (Better)
Delete and recreate the StatefulSets with `configMap.name` set to non-hashed names:

```bash
kubectl delete statefulset wazuh-indexer -n wazuh
kubectl delete statefulset wazuh-manager-master -n wazuh
kubectl delete statefulset wazuh-manager-worker -n wazuh

# Then apply with updated names
kubectl apply -k .tmp/wazuh-kubernetes/custom-deploy/
```

### Option 3: Manual ConfigMap Creation (Current Workaround)

Save this as `wazuh-configmaps-fix.yaml` and apply after deployment:

```yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: indexer-conf-REPLACE_WITH_HASH
  namespace: wazuh
data:
  opensearch.yml: |
    cluster.name: wazuh-cluster
    node.name: ${NODE_NAME}
    path.data: /var/lib/wazuh-indexer
    path.logs: /var/log/wazuh-indexer
    bootstrap.memory_lock: true
    network.host: 0.0.0.0
    http.port: 9200
    transport.tcp.port: 9300
    discovery.seed_hosts:
      - wazuh-indexer-0
    cluster.initial_master_nodes:
      - wazuh-indexer-0
    plugins.security.ssl.http.enabled: true
    plugins.security.ssl.http.pemcert_filepath: /usr/share/wazuh-indexer/certs/node.pem
    plugins.security.ssl.http.pemkey_filepath: /usr/share/wazuh-indexer/certs/node-key.pem
    plugins.security.ssl.http.pemtrustedcas_filepath: /usr/share/wazuh-indexer/certs/root-ca.pem
    plugins.security.ssl.transport.enabled: true
    plugins.security.ssl.transport.pemcert_filepath: /usr/share/wazuh-indexer/certs/node.pem
    plugins.security.ssl.transport.pemkey_filepath: /usr/share/wazuh-indexer/certs/node-key.pem
    plugins.security.ssl.transport.pemtrustedcas_filepath: /usr/share/wazuh-indexer/certs/root-ca.pem
    plugins.security.ssl.transport.enforce_hostname_verification: false
    plugins.security.ssl.transport.resolve_hostname: false
    plugins.security.authcz.admin_dn:
      - "CN=admin,OU=Wazuh,O=Wazuh,L=California,C=US"
    plugins.security.check_snapshot_restore_write_privileges: true
    plugins.security.enable_snapshot_restore_privilege: true
    plugins.security.nodes_dn:
      - "CN=wazuh-indexer,OU=Wazuh,O=Wazuh,L=California,C=US"
    plugins.security.restapi.roles_enabled:
      - "all_access"
      - "security_rest_api_access"
  internal_users.yml: |
    _meta:
      type: internalusers
      config_version: 2
    admin:
      hash: "$2y$10$M6xUq4eX8K8Zv4c5Yc5YdO7eG9dL7eG9dL7eG9dL7eG9dL7eG9dL7e"
      reserved: true
      backend_roles:
        - "admin"
      description: "Admin user"
---
apiVersion: v1
kind: ConfigMap
metadata:
  name: wazuh-conf-REPLACE_WITH_HASH
  namespace: wazuh
data:
  master.conf: |
    <ossec_config>
      <cluster>
        <name>wazuh</name>
        <node_name>master</node_name>
        <node_type>master</node_type>
        <key>9d48f82a3e5b3a2d6c7e8f9a0b1c2d3e</key>
        <port>1516</port>
        <bind_addr>0.0.0.0</bind_addr>
        <nodes>
          <node>wazuh-indexer</node>
        </nodes>
        <hidden>no</hidden>
        <disabled>no</disabled>
      </cluster>
    </ossec_config>
  worker.conf: |
    <ossec_config>
      <cluster>
        <name>wazuh</name>
        <node_name>worker</node_name>
        <node_type>worker</node_type>
        <key>9d48f82a3e5b3a2d6c7e8f9a0b1c2d3e</key>
        <port>1516</port>
        <bind_addr>0.0.0.0</bind_addr>
        <nodes>
          <node>wazuh-manager-master-0.wazuh-cluster</node>
        </nodes>
        <hidden>no</hidden>
        <disabled>no</disabled>
      </cluster>
    </ossec_config>
```

**Note:** Replace `REPLACE_WITH_HASH` with the actual hash suffix from the StatefulSet.
