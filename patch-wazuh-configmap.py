"""
Patch the Wazuh ConfigMap to add the Shuffle SOAR integration block.
This script reads the current ConfigMap, adds the integration block,
and applies the updated ConfigMap.
"""
import subprocess
import json
import sys

# The integration block to add before </ossec_config>
INTEGRATION_BLOCK = """
  <!-- Shuffle SOAR Integration -->
  <integration>
    <name>slack</name>
    <hook_url>http://shuffle-backend.security-ops.svc.cluster.local:5001/api/v1/hooks/webhook_4ec040d0-2ba5-4135-bf69-050cad1d115b</hook_url>
    <level>3</level>
    <alert_format>json</alert_format>
  </integration>
"""

NAMESPACE = "wazuh"
CONFIGMAP_NAME = "wazuh-conf-2t66md6694"

def run_kubectl(args):
    """Run a kubectl command and return stdout."""
    result = subprocess.run(
        ["kubectl"] + args,
        capture_output=True,
        text=True,
        encoding="utf-8"
    )
    if result.returncode != 0:
        print(f"kubectl error: {result.stderr}", file=sys.stderr)
        sys.exit(1)
    return result.stdout

def main():
    # 1. Get current ConfigMap as JSON
    print("Fetching current ConfigMap...")
    cm_json = run_kubectl(["get", "configmap", CONFIGMAP_NAME, "-n", NAMESPACE, "-o", "json"])
    cm = json.loads(cm_json)
    
    # 2. Get current master.conf content
    master_conf = cm["data"]["master.conf"]
    
    # 3. Remove any existing Shuffle integration block (may have old "custom" type)
    import re
    old_block_pattern = r'\s*<!-- Shuffle SOAR Integration -->\s*<integration>.*?</integration>\s*'
    master_conf = re.sub(old_block_pattern, '\n  ', master_conf, flags=re.DOTALL).rstrip() + '\n'
    
    # 4. Add integration block before the first </ossec_config>
    # Find the first occurrence of </ossec_config>
    insert_point = master_conf.find("</ossec_config>")
    if insert_point == -1:
        print("ERROR: Could not find </ossec_config> in master.conf", file=sys.stderr)
        sys.exit(1)
    
    # Insert the integration block before </ossec_config>
    new_conf = master_conf[:insert_point] + INTEGRATION_BLOCK + master_conf[insert_point:]
    
    # 5. Update the ConfigMap
    cm["data"]["master.conf"] = new_conf
    
    # 6. Write the updated ConfigMap JSON to a temp file and apply
    import tempfile
    import os
    
    with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False, encoding='utf-8') as f:
        json.dump(cm, f, ensure_ascii=False)
        temp_file = f.name
    
    try:
        print("Applying updated ConfigMap...")
        result = subprocess.run(
            ["kubectl", "apply", "-f", temp_file],
            capture_output=True,
            text=True,
            encoding="utf-8"
        )
        print(result.stdout)
        if result.returncode != 0:
            print(f"Error: {result.stderr}", file=sys.stderr)
            sys.exit(1)
        print("ConfigMap updated successfully!")
    finally:
        os.unlink(temp_file)
    
    # 7. Restart the Wazuh manager to pick up the new config
    print("Restarting Wazuh manager...")
    result = subprocess.run(
        ["kubectl", "rollout", "restart", "statefulset/wazuh-manager-master", "-n", NAMESPACE],
        capture_output=True,
        text=True,
        encoding="utf-8"
    )
    print(result.stdout)
    if result.returncode != 0:
        print(f"Error: {result.stderr}", file=sys.stderr)
        sys.exit(1)
    print("Wazuh manager restart initiated.")

if __name__ == "__main__":
    main()