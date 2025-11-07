"""
Check Event Hub Connection String Permissions
This script helps diagnose CBS Token authentication errors
"""
import os
import sys

print("=" * 60)
print("Event Hub Connection String Permission Checker")
print("=" * 60)

conn_str = os.environ.get('EVENTHUB_CONNECTION_STRING')
eventhub_name = os.environ.get('EVENTHUB_NAME')

if not conn_str:
    print("\n❌ EVENTHUB_CONNECTION_STRING is not set")
    sys.exit(1)

print("\n1. Parsing Connection String...")

# Parse connection string components
components = {}
for part in conn_str.split(';'):
    if '=' in part:
        key, value = part.split('=', 1)
        components[key] = value

print(f"   ✓ Endpoint: {components.get('Endpoint', '❌ MISSING')}")
print(f"   ✓ SharedAccessKeyName: {components.get('SharedAccessKeyName', '❌ MISSING')}")
print(f"   ✓ SharedAccessKey: {'Present' if components.get('SharedAccessKey') else '❌ MISSING'}")
print(f"   ✓ EntityPath: {components.get('EntityPath', 'Not in connection string')}")

# Check for critical missing components
if not components.get('SharedAccessKeyName'):
    print("\n❌ ERROR: SharedAccessKeyName is missing!")
    print("   Your connection string must include a shared access policy name")
    sys.exit(1)

if not components.get('SharedAccessKey'):
    print("\n❌ ERROR: SharedAccessKey is missing!")
    print("   Your connection string must include a shared access key")
    sys.exit(1)

print("\n2. Connection String Format: ✓ Valid")

print("\n" + "=" * 60)
print("Common Causes of 'amqp:unauthorized-access' Error:")
print("=" * 60)

print("""
❌ WRONG: Using a connection string from a different Event Hub or namespace
   Solution: Get the connection string from YOUR specific Event Hub

❌ WRONG: Shared Access Policy doesn't have 'Send' permission
   Solution: Policy needs at least 'Send' claims (or 'Manage' which includes Send)

❌ WRONG: Using an expired or regenerated key
   Solution: If keys were regenerated, get the new connection string

❌ WRONG: Using namespace-level key without proper EntityPath
   Solution: Use Event Hub-level connection string instead

❌ WRONG: Connection string copied incorrectly (truncated/extra characters)
   Solution: Re-copy the connection string carefully
""")

print("=" * 60)
print("How to Get the CORRECT Connection String:")
print("=" * 60)

print("""
Option 1: Azure Portal (Recommended)
------------------------------------
1. Go to: Azure Portal → Your Event Hub Namespace → Event Hubs
2. Click on YOUR specific Event Hub name
3. Go to: Settings → Shared access policies
4. If no policy exists, click "+ Add" and create one with 'Send' permission
5. Click on the policy name
6. Copy the "Connection string–primary key"
   - Should include: Endpoint, SharedAccessKeyName, SharedAccessKey, EntityPath
   - EntityPath should match your Event Hub name

Option 2: Azure CLI
-------------------
# For Event Hub-level connection string (RECOMMENDED):
az eventhubs eventhub authorization-rule keys list \\
    --resource-group <your-resource-group> \\
    --namespace-name <your-namespace> \\
    --eventhub-name <your-eventhub> \\
    --name <policy-name> \\
    --query primaryConnectionString \\
    --output tsv

# Check what policies exist:
az eventhubs eventhub authorization-rule list \\
    --resource-group <your-resource-group> \\
    --namespace-name <your-namespace> \\
    --eventhub-name <your-eventhub> \\
    --output table

# Create a new Send policy if needed:
az eventhubs eventhub authorization-rule create \\
    --resource-group <your-resource-group> \\
    --namespace-name <your-namespace> \\
    --eventhub-name <your-eventhub> \\
    --name SendPolicy \\
    --rights Send
""")

print("\n" + "=" * 60)
print("Verification Steps:")
print("=" * 60)

policy_name = components.get('SharedAccessKeyName', 'UNKNOWN')
endpoint = components.get('Endpoint', '')
namespace = endpoint.replace('sb://', '').replace('.servicebus.windows.net/', '') if endpoint else 'UNKNOWN'

print(f"""
Current Configuration:
- Namespace: {namespace}
- Policy Name: {policy_name}
- Entity Path: {components.get('EntityPath', eventhub_name or 'MISSING')}

Next Steps:
1. Verify this policy exists in Azure Portal:
   Event Hub → Shared access policies → Look for "{policy_name}"

2. Check the policy has 'Send' permission:
   Click on "{policy_name}" → Verify 'Send' is checked

3. If policy doesn't exist or lacks Send permission:
   - Create a new policy with Send permission
   - Get its connection string
   - Update EVENTHUB_CONNECTION_STRING in your Azure Web App

4. After updating, restart your Azure Web App
""")

print("=" * 60)
