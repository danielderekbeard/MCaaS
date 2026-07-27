# MCaaS Power Management Guide

This guide provides quick commands to safely suspend and resume the MCaaS stack (PostgreSQL, OpenSearch, Wazuh, Shuffle, Zammad, and CISO Assistant) running on your Kubernetes cluster.

Instead of destroying the cluster or deleting deployments, this process scales your compute resources (Pods) down to `0`. This triggers a graceful shutdown `SIGTERM` signal, ensuring no data corruption occurs while preserving all your databases and configurations on their Persistent Volumes.

---

## Prerequisites

Ensure the following before running the power management commands:
* The `power_manager.py` script is saved in the same directory as `deploy.py`.
* You have an active connection to your Kubernetes cluster (`kubectl` must be authenticated).

---

## Commands

### 1. Graceful Shutdown
To suspend the stack and stop all active containers, run:

```bash
python power_manager.py shutdown