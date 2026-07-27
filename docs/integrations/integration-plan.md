# MCaaS Integration Plan: From Wazuh Alert to Action

It's great that you have your first workstation reporting to Wazuh. That's the first critical step in bringing the MCaaS stack to life. Now, let's unlock the power of the other systems by integrating them.

The goal is to create an automated workflow where a security alert from Wazuh triggers an orchestrated response, creates a ticket for tracking, and provides data for compliance and risk management.

## What to Expect from the Stack

Here’s the journey of a security alert through your newly integrated MCaaS stack:

1.  **Detection (Wazuh - "Deimos"):** Wazuh detects a suspicious event on your managed workstation (e.g., malware signature, brute-force login attempt, anomalous process). It generates a detailed alert.

2.  **Automation & Enrichment (Shuffle - "Kydoimos"):** This is where the magic happens. A Shuffle workflow will automatically:
    *   **Receive** the alert from Wazuh.
    *   **Enrich** the data. For example, if the alert contains an IP address, Shuffle can check threat intelligence feeds (like VirusTotal or AbuseIPDB) to see if it's malicious.
    *   **Orchestrate** a response. It can execute actions like querying other systems or, in more advanced setups, trigger a defensive action (like isolating a host via Wazuh's active response).

3.  **Incident Tracking (Zammad - "Alala"):** After enrichment, the Shuffle workflow will connect to Zammad and automatically:
    *   **Create a ticket** for a human analyst to review.
    *   **Populate the ticket** with the original Wazuh alert, all the enriched data from Shuffle, and a summary of any actions taken. This gives your security team a complete, actionable view of the incident in one place.

4.  **Governance & Reporting (CISO Assistant - "Strategos"):** While direct integration is a future step, CISO Assistant is where you manage the bigger picture. After an incident is resolved in Zammad, you can:
    *   Log the incident in CISO Assistant to track risk.
    *   Link the incident to specific controls and assets.
    *   Generate reports for compliance audits and management, demonstrating effective incident response.

## Your Integration Plan

Let's get these systems talking to each other. This plan involves configuring each tool to connect to the others.

### Step 1: Configure Wazuh to Forward Alerts to Shuffle

Wazuh needs to send its alerts to Shuffle. The most robust way to do this is by using a webhook output in Wazuh that triggers a Shuffle workflow.

1.  **Create a Shuffle Webhook:**
    *   Log into Shuffle (`http://kydoimos.mcaas.example.com`).
    *   Create a new workflow.
    *   The trigger for the workflow should be a **Webhook**.
    *   Copy the generated webhook URL. You will need this for the Wazuh configuration.

2.  **Configure Wazuh's `ossec.conf`:**
    *   You need to modify the Wazuh manager's configuration file to add an `integration` block.
    *   First, `exec` into the Wazuh manager pod:
        ```bash
        kubectl exec -it -n wazuh statefulset/wazuh-manager-master -- /bin/bash
        ```
    *   Inside the pod, open `/var/ossec/etc/ossec.conf` with an editor like `vi`.
    *   Add the following block, pasting your Shuffle webhook URL. This tells Wazuh to send all alerts with a rule level of 3 or higher to Shuffle.
        ```xml
        <integration>
          <name>shuffle</name>
          <hook_url>PASTE_YOUR_SHUFFLE_WEBHOOK_URL_HERE</hook_url>
          <level>3</level>
          <format>json</format>
        </integration>
        ```
    *   Save the file and exit the editor.

3.  **Restart the Wazuh Manager:**
    *   To apply the changes, you must restart the Wazuh manager.
        ```bash
        kubectl rollout restart statefulset/wazuh-manager-master -n wazuh
        ```
    *   Wazuh alerts should now appear as events in your Shuffle workflow.

### Step 2: Configure Shuffle to Create Tickets in Zammad

Now, let's have Shuffle create a ticket in Zammad when it processes an alert.

1.  **Generate a Zammad API Token:**
    *   Log into Zammad (`http://alala.mcaas.example.com`) as an administrator.
    *   Go to **Profile -> Token Access**.
    *   Create a new token with `ticket.agent` permissions.
    *   Copy the generated API token.

2.  **Add Zammad Credentials to Shuffle:**
    *   In Shuffle, go to **Admin -> Credentials**.
    *   Click **"New Credential"**.
    *   Give it a name (e.g., `zammad-api-key`).
    *   For the value, paste the Zammad API token you just created.

3.  **Use the Zammad App in a Shuffle Workflow:**
    *   In your Shuffle workflow, add a new action node.
    *   Search for the **Zammad** app.
    *   Select the `create_ticket` action.
    *   In the action's parameters:
        *   **`zammad_url`**: `http://mcaas-zammad-nginx.managed-it.svc.cluster.local:8080` (This is the internal Kubernetes service URL for Zammad).
        *   **`api_key`**: Select the `zammad-api-key` credential you created.
        *   **`title`**: Map the title from the Wazuh alert (e.g., `{{.webhook_trigger.rule.description}}`).
        *   **`group`**: `Users` (or another group in your Zammad instance).
        *   **`customer`**: The customer email or ID. You can hardcode one for now.
        *   **`article_body`**: Map the full JSON of the Wazuh alert here to include all details (e.g., `{{.webhook_trigger | json_pretty}}`).

Now, when a Wazuh alert hits Shuffle, a ticket will be automatically created in Zammad with all the alert details.

### Step 3: Configure Shuffle to Use the Wazuh API

For enrichment or active response, Shuffle needs to communicate back to the Wazuh API.

1.  **Find the Wazuh API Credentials:**
    *   The default password for the `wazuh-wui` user (which the API uses) is hardcoded in the upstream Wazuh deployment. You will need to reset it to something secure.
    *   The script `scripts/reset_wazuh_password.py` in your repository is perfect for this.

2.  **Reset the `wazuh-wui` Password:**
    *   First, copy the script into the Wazuh manager pod:
        ```bash
        kubectl cp c:\projects\skyddex\MCaaS\scripts\reset_wazuh_password.py wazuh/wazuh-manager-master-0:/tmp/reset.py -c wazuh-manager
        ```
    *   Now, `exec` into the pod:
        ```bash
        kubectl exec -it -n wazuh statefulset/wazuh-manager-master -- /bin/bash
        ```
    *   Run the script to set a new, strong password. Replace `YourNewStrongPassword` with a secure password of your choice.
        ```bash
        python3 /tmp/reset.py wazuh-wui 'YourNewStrongPassword'
        ```
    *   Make a note of this new password.

3.  **Add Wazuh Credentials to Shuffle:**
    *   In Shuffle, go to **Admin -> Credentials**.
    *   Create two new credentials:
        *   Name: `wazuh-api-user`, Value: `wazuh-wui`
        *   Name: `wazuh-api-pass`, Value: `YourNewStrongPassword`

4.  **Use the Wazuh App in a Shuffle Workflow:**
    *   Add a **Wazuh** app node to your workflow.
    *   Select an action, like `get_agent_info`.
    *   In the action's parameters:
        *   **`hostname`**: `https://wazuh.wazuh.svc.cluster.local` (The internal service URL for the Wazuh manager).
        *   **`username`**: Select the `wazuh-api-user` credential.
        *   **`password`**: Select the `wazuh-api-pass` credential.
        *   **`agent_id`**: Map the agent ID from the Wazuh alert (e.g., `{{.webhook_trigger.agent.id}}`).

With this final piece, you have a fully integrated, automated security operations pipeline. You can now build more sophisticated Shuffle workflows to handle different types of alerts. Good luck!