# MCaaS Retry & Timeout Recommendations

> **Status: DRAFT — Not for commit**  
> Analysis of current timeout and retry mechanisms, with recommendations for improvements.

---

## Current Timeouts in `deploy.py`

| Component | Resource Type | Current Timeout | Wait Strategy |
|-----------|-------------|-----------------|---------------|
| PostgreSQL | Deployment | 5 min | `wait_for_resource()` — 3-tier fallback |
| OpenSearch | StatefulSet | 10 min | `wait_for_resource()` — 3-tier fallback |
| Wazuh Manager | Deployment | 10 min | `kubectl wait --for=condition=available` |
| Wazuh Indexer | StatefulSet | 10 min | `kubectl wait --for=condition=ready` |
| Wazuh Dashboard | Deployment | 10 min | `kubectl wait --for=condition=available` |
| Shuffle | Deployment | 8 min | `wait_for_resource()` — 3-tier fallback |
| Zammad | Deployment | 8 min | `wait_for_resource()` — 3-tier fallback |
| CISO Assistant | Deployment | 8 min | `wait_for_resource()` — 3-tier fallback |

---

## Current Retry Mechanisms

### `wait_for_resource()` — 3-Tier Fallback
1. **Tier 1**: `kubectl wait --for=condition=available deployment/<name>` — Standard deployment wait
2. **Tier 2**: `kubectl wait --for=condition=ready statefulset/<name>` — StatefulSet label-based wait
3. **Tier 3**: Polling loop checking `kubectl get statefulset <name> -o jsonpath={.status.readyReplicas}` every 10 seconds

### `run_command()` — Subprocess Wrapper
- No built-in retry mechanism
- Raises `CalledProcessError` on failure
- Supports dry-run mode
- Logs command output on failure

### `helm upgrade --install`
- Helm's built-in retry: If a release is in "failed" state, `upgrade --install` will attempt to upgrade it
- No retry on Helm command failure itself — deploy.py moves to the next component

---

## Recommended Changes

### 1. Increase Image Pull Timeout Handling

**Problem**: On slow networks or first-time deployments, pulling large container images (OpenSearch ~1.3GB, Wazuh ~1GB+) can exceed wait timeouts even before the container starts initializing.

**Recommendation**: Add a pre-wait image pull verification step:

```python
def wait_for_image_pull(namespace, label_selector, timeout=600):
    """Wait until all pods matching the label have their images pulled."""
    logger.info(f"Waiting for image pull for {label_selector} in {namespace}...")
    start = time.time()
    while time.time() - start < timeout:
        result = run_command(
            f"kubectl get pods -n {namespace} -l {label_selector} "
            f"-o jsonpath='{{.items[*].status.containerStatuses[*].ready}}'",
            check=False
        )
        # If any container has ImagePullBackOff, log it
        # If all containers are ready or in CrashLoopBackOff, images are pulled
        time.sleep(15)
    return False  # timed out
```

### 2. Add Exponential Backoff to `wait_for_resource()`

**Problem**: The current Tier 3 polling uses a fixed 10-second interval. During slow initialization, this creates unnecessary log noise while not improving recovery speed.

**Recommendation**: Use exponential backoff starting at 5 seconds, capping at 60 seconds:

```python
interval = 5  # Start at 5 seconds
max_interval = 60
while time.time() - start < timeout:
    # ... check readiness ...
    time.sleep(interval)
    interval = min(interval * 1.5, max_interval)
```

### 3. Add Helm Release Status Validation After Timeout

**Problem**: When `wait_for_resource()` times out, it reports failure even though the pod may still be progressing. Conversely, when Helm itself times out (e.g., `--timeout 10m`), it marks the release as "failed" even if the pod eventually becomes Ready.

**Recommendation**: After a timeout, check both Helm release status and pod readiness:

```python
def validate_deployment_health(release_name, namespace):
    """Check actual deployment health even if Helm reports failure."""
    # Check Helm release status
    helm_status = run_command(
        f"helm status {release_name} -n {namespace} -o json",
        check=False
    )
    # Check pod readiness independently
    pod_status = run_command(
        f"kubectl get pods -n {namespace} -l app.kubernetes.io/instance={release_name} "
        f"-o jsonpath='{{.items[*].status.phase}}'",
        check=False
    )
    # If pods are Running/Ready, consider it a success even if Helm says failed
    return "Running" in pod_status or "Succeeded" in pod_status
```

### 4. Add PVC Binding Wait

**Problem**: On k3s with `local-path` StorageClass and `WaitForFirstConsumer`, PVCs remain in "Pending" until a pod is scheduled. If the pod scheduling fails (e.g., node selector mismatch), the PVC will never bind, and the deployment will hang.

**Recommendation**: Add a PVC binding check before waiting for pods:

```python
def wait_for_pvc_binding(namespace, pvc_name, timeout=120):
    """Wait for a PersistentVolumeClaim to be bound."""
    start = time.time()
    while time.time() - start < timeout:
        result = run_command(
            f"kubectl get pvc {pvc_name} -n {namespace} "
            f"-o jsonpath='{{.status.phase}}'",
            check=False
        )
        if result.strip() == "Bound":
            return True
        time.sleep(5)
    logger.warning(f"PVC {pvc_name} in {namespace} not bound after {timeout}s")
    return False
```

### 5. Add Helm Install Retry With Increased Timeout

**Problem**: `helm upgrade --install` is called once per component. If it fails, the entire deployment stops.

**Recommendation**: Add a retry wrapper for Helm operations:

```python
def helm_upgrade_with_retry(release_name, chart, namespace, values_file,
                             max_retries=2, base_timeout=600):
    """Run helm upgrade --install with retries and progressive timeout increase."""
    for attempt in range(max_retries + 1):
        timeout = base_timeout * (attempt + 1)  # Increase timeout on each retry
        try:
            run_command(
                f"helm upgrade --install {release_name} {chart} "
                f"--namespace {namespace} --values {values_file} "
                f"--timeout {timeout}s",
                check=True
            )
            return True
        except CalledProcessError as e:
            if attempt < max_retries:
                logger.warning(
                    f"Helm install attempt {attempt + 1} failed, "
                    f"retrying with {timeout}s timeout..."
                )
                # Clean up failed release before retry
                run_command(f"helm rollback {release_name} -n {namespace}", check=False)
            else:
                logger.error(f"Helm install failed after {max_retries + 1} attempts")
                raise
    return False
```

### 6. Increase Recommended Timeouts for Production

| Component | Current | Recommended (Min) | Recommended (Slow Network) | Rationale |
|-----------|---------|-------------------|----------------------------|-----------|
| PostgreSQL | 5 min | 5 min | 10 min | Small image, fast init |
| OpenSearch | 10 min | 15 min | 20 min | Large image (1.3GB), slow plugin init |
| Wazuh Manager | 10 min | 10 min | 15 min | Multiple init containers |
| Wazuh Indexer | 10 min | 10 min | 15 min | Large image, certificate setup |
| Wazuh Dashboard | 10 min | 10 min | 15 min | Depends on indexer |
| Shuffle | 8 min | 10 min | 15 min | Backend depends on OpenSearch |
| Zammad | 8 min | 10 min | 15 min | Multiple init containers, DB migration |
| CISO Assistant | 8 min | 10 min | 15 min | DB schema initialization |

### 7. Add Health Check Probes After Deployment

**Problem**: Pod readiness doesn't guarantee service health. An application can report Ready but fail to serve requests (e.g., OpenSearch security plugin initialization).

**Recommendation**: Add HTTP health checks after pod readiness:

```python
def check_service_health(url, expected_status=200, timeout=120, interval=10):
    """Poll a service HTTP endpoint until it responds with expected status."""
    import urllib.request
    import urllib.error
    start = time.time()
    while time.time() - start < timeout:
        try:
            response = urllib.request.urlopen(url, timeout=5)
            if response.getcode() == expected_status:
                return True
        except (urllib.error.URLError, urllib.error.HTTPError, OSError):
            pass
        time.sleep(interval)
    return False
```

Suggested health check endpoints:

| Component | Health Endpoint | Expected |
|-----------|----------------|----------|
| PostgreSQL | `kubectl exec` — `pg_isready` | exit 0 |
| OpenSearch | `https://<svc>:9200/_cluster/health` | 200 |
| Wazuh Manager | `https://<svc>:55000/?` | 200 |
| Shuffle | `http://<svc>:3000/api/v1/health` | 200 |
| Zammad | `http://<svc>:8080/` | 200 or 302 |
| CISO Assistant | `http://<svc>:80/api/v1/health` | 200 |

---

## Summary of Priority Changes

| Priority | Change | Effort | Impact |
|----------|--------|--------|--------|
| 🔴 High | Increase OpenSearch timeout to 15-20 min | Low | Prevents most common deployment failure |
| 🔴 High | Add Helm release status validation after timeout | Medium | Prevents false "failed" states |
| 🟡 Medium | Add exponential backoff to polling | Low | Reduces log noise, faster detection |
| 🟡 Medium | Add Helm install retry with progressive timeout | Medium | Recovers from transient failures |
| 🟡 Medium | Add PVC binding wait | Low | Prevents hangs on storage issues |
| 🟢 Low | Add HTTP health check probes | Medium | Catches "Ready but not healthy" cases |
| 🟢 Low | Add image pull verification | Medium | Better progress visibility |

---

*See also: [Installation Guide](./installation-guide.md) | [Services Matrix](./services-matrix.md) | [Configuration Matrix](./configuration-matrix.md) | [Session Changes](./session-changes.md)*