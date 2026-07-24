Here are the corrected and updated Helm repository URLs for your core services, along with the required syntax changes to patch your deploy.ps1 script.  
The most significant change to your script will be for **CISO Assistant** and **Shuffle**. Both projects have transitioned to using modern OCI (Open Container Initiative) registries rather than traditional Helm HTTP repositories. OCI registries do not use the helm repo add command; instead, you pass the URL directly to the helm install or helm upgrade command.

### **1\. Wazuh**

The Wazuh Kubernetes deployment has been moved to their official GitHub Pages repository.

* **Remove:** helm repo add wazuh \[old-url\]  
* **Add:** \`\`\`powershell  
  helm repo add wazuh https://wazuh.github.io/wazuh-kubernetes  
  helm repo update  
  helm install mcaas-wazuh wazuh/wazuh \-n security-ops \--create-namespace

### **2\. Zammad**

Zammad’s chart is no longer hosted on the Bitnami index. It is officially maintained in their own Helm repository.

* **Remove:** Your current Zammad bitnami reference.  
* **Add:**  
  PowerShell  
  helm repo add zammad https://zammad.github.io/zammad\-helm  
  helm repo update  
  helm install zammad zammad/zammad \-n managed\-it \-\-create-namespace

### **3\. CISO Assistant (Community Edition)**

Intuitem recently deprecated their old intuitem.github.io/ca-helm-chart repository. The chart is now exclusively distributed via the GitHub Container Registry (GHCR) as an OCI artifact.

* **Remove:** Any helm repo add ciso-assistant command.  
* **Update your install command to:**  
  PowerShell  
  helm install ciso\-assistant oci://ghcr.io/intuitem/helm\-charts/ce/ciso\-assistant \-n grc \-\-create-namespace

  *(Note: Remember to disable the bundled PostgreSQL in your values.yaml for CISO Assistant as we discussed previously, connecting it to your external Longhorn-backed Postgres StatefulSet instead).*

### **4\. Shuffle (SOAR)**

The charts.shuffle.dev domain is inactive. The Shuffle community recently finalized and merged an official Helm chart directly into their primary repository, which is also published as an OCI artifact on GHCR.

* **Remove:** helm repo add shuffle https://charts.shuffle.dev  
* **Update your install command to:**  
  PowerShell  
  helm install mcaas\-shuffle oci://ghcr.io/shuffle/charts/shuffle \-n security\-ops \-\-create-namespace

  *(Alternatively, you can clone the [Shuffle GitHub repository](https://github.com/Shuffle/Shuffle) and run helm install mcaas-shuffle ./chart from the local directory).*

### **Quick Script Cleanup Tip**

Since you are updating your deploy.ps1, make sure that anywhere you are using a bare kubectl apply for your namespaces (grc, managed-it, security-ops), you switch it to kubectl create namespace \<name\> \--dry-run=client \-o yaml | kubectl apply \-f \-. This will gracefully handle creating the namespaces without throwing the missing last-applied-configuration annotation warnings you were seeing earlier.  
Let me know if you hit any snags patching this in or if you're ready to tackle the Longhorn/Postgres storage pipeline next\!