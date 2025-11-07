# CBS Token Authentication Error - Troubleshooting Guide

## The Problem

You're seeing:
- ✓ "Event Hub producer initialized successfully with connection string"
- ❌ Then: "CBS Token authentication failed" when trying to send

This means the producer **initializes** fine but **fails when actually sending data**.

## Root Cause

The CBS Token error when using a connection string typically happens when:

1. **Connection string has EntityPath BUT you're also passing eventhub_name parameter**
   - This creates a conflict
   - The SDK gets confused about which Event Hub to use

2. **Connection string is missing SharedAccessKey**
   - Connection string format must be: `Endpoint=sb://NAMESPACE.servicebus.windows.net/;SharedAccessKeyName=POLICY;SharedAccessKey=KEY;EntityPath=EVENTHUB`
   - If EntityPath is missing, you MUST provide eventhub_name parameter

## Solutions

### Option 1: Connection String WITH EntityPath (Recommended)

Get the **Event Hub-level** connection string (not namespace-level):

```bash
# Get Event Hub connection string (includes EntityPath)
az eventhubs eventhub authorization-rule keys list \
    --resource-group <resource-group> \
    --namespace-name <namespace> \
    --eventhub-name <eventhub-name> \
    --name RootManageSharedAccessKey \
    --query primaryConnectionString \
    --output tsv
```

Set in Azure Web App:
```
EVENTHUB_CONNECTION_STRING=Endpoint=sb://yournamespace.servicebus.windows.net/;SharedAccessKeyName=RootManageSharedAccessKey;SharedAccessKey=YOURKEY;EntityPath=youreventhub
```

**DO NOT set** `EVENTHUB_NAME` when using this approach.

### Option 2: Connection String WITHOUT EntityPath

Get the **Namespace-level** connection string:

```bash
# Get namespace connection string (NO EntityPath)
az eventhubs namespace authorization-rule keys list \
    --resource-group <resource-group> \
    --namespace-name <namespace> \
    --name RootManageSharedAccessKey \
    --query primaryConnectionString \
    --output tsv
```

Set BOTH in Azure Web App:
```
EVENTHUB_CONNECTION_STRING=Endpoint=sb://yournamespace.servicebus.windows.net/;SharedAccessKeyName=RootManageSharedAccessKey;SharedAccessKey=YOURKEY
EVENTHUB_NAME=youreventhub
```

## How to Diagnose

Run the test script:
```powershell
python test_config.py
```

Look for:
```
Connection string contains EntityPath: ✓ YES
EntityPath value: your-eventhub-name
```

If EntityPath is present → **Remove EVENTHUB_NAME variable**
If EntityPath is missing → **Keep EVENTHUB_NAME variable**

## Azure Web App Configuration

1. Go to Azure Portal → Your Web App → Configuration → Application Settings

2. Check your current settings:
   - If `EVENTHUB_CONNECTION_STRING` contains `EntityPath=`:
     - ✓ Keep `EVENTHUB_CONNECTION_STRING`
     - ❌ DELETE `EVENTHUB_NAME`
   
   - If `EVENTHUB_CONNECTION_STRING` does NOT contain `EntityPath=`:
     - ✓ Keep `EVENTHUB_CONNECTION_STRING`
     - ✓ Keep `EVENTHUB_NAME` (set to your Event Hub name)

3. Click "Save" and restart the Web App

## Verification

After fixing, your logs should show:
```
=== Event Hub Configuration ===
EVENTHUB_NAME: your-eventhub (or None)
EVENTHUB_CONNECTION_STRING present: True
Connection string contains EntityPath: True (or False)
Initializing Event Hub producer with connection string...
EntityPath found in connection string, using it directly (or: Using EVENTHUB_NAME parameter)
✓ Event Hub producer initialized successfully with connection string
Creating event batch...
Creating event data...
Adding event to batch...
Sending batch to Event Hub...
✓ Successfully sent event to Event Hub
```

## Common Mistakes

❌ Having BOTH EntityPath in connection string AND EVENTHUB_NAME variable
❌ Connection string missing SharedAccessKey
❌ Using wrong Event Hub name in EVENTHUB_NAME
❌ Whitespace or quotes in environment variables

## Still Having Issues?

Check:
1. Event Hub exists and name is correct
2. SAS policy has "Send" permission
3. Network connectivity (firewall rules)
4. Connection string not truncated or corrupted
