#!/usr/bin/env python3
"""Reset Wazuh API user passwords in rbac.db using werkzeug's password hashing.

This script updates the password hash in the rbac.db SQLite database
for the specified user. It must be run inside the wazuh-manager pod.
"""

import sqlite3
import sys

# werkzeug is available inside the Wazuh manager pod
from werkzeug.security import generate_password_hash


def reset_password(db_path, username, new_password):
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # Check if user exists
    cursor.execute("SELECT id, username FROM users WHERE username = ?", (username,))
    user = cursor.fetchone()
    if not user:
        print(f"ERROR: User '{username}' not found in database")
        conn.close()
        sys.exit(1)

    print(f"Found user: id={user[0]}, username={user[1]}")

    # Generate password hash using werkzeug (same as Wazuh uses)
    password_hash = generate_password_hash(new_password)
    print(f"Generated hash: {password_hash[:50]}...")

    # Update the password
    cursor.execute(
        "UPDATE users SET password = ? WHERE username = ?", (password_hash, username)
    )
    conn.commit()

    # Verify
    cursor.execute(
        "SELECT username, password FROM users WHERE username = ?", (username,)
    )
    result = cursor.fetchone()
    print(
        f"Updated user '{result[0]}' password hash (first 50 chars): {result[1][:50]}..."
    )

    conn.close()
    print("Password updated successfully!")


if __name__ == "__main__":
    db_path = "/var/ossec/api/configuration/security/rbac.db"
    username = "wazuh-wui"
    new_password = "MyS3cr37P450r.*-"

    if len(sys.argv) > 1:
        username = sys.argv[1]
    if len(sys.argv) > 2:
        new_password = sys.argv[2]

    print(f"Resetting password for user '{username}' in {db_path}")
    reset_password(db_path, username, new_password)
