"""
Verify Event Hub Name and Access
This script checks if the Event Hub exists and is accessible
"""
import os
import sys

# Get configuration
EVENTHUB_CONNECTION_STRING = os.environ.get('EVENTHUB_CONNECTION_STRING', '').strip().strip('"').strip("'")
EVENTHUB_NAME = os.environ.get('EVENTHUB_NAME', '').strip().strip('"').strip("'")

if not EVENTHUB_CONNECTION_STRING:
    print("❌ EVENTHUB_CONNECTION_STRING not set")
    sys.exit(1)

if not EVENTHUB_NAME:
    print("❌ EVENTHUB_NAME not set")
    sys.exit(1)

print("=" * 70)
print("Event Hub Verification")
print("=" * 70)
print(f"\nNamespace: ag-cla-tst-ehub-01.servicebus.windows.net")
print(f"Event Hub Name: {EVENTHUB_NAME}")
print()

try:
    from azure.eventhub import EventHubProducerClient
    
    print("Testing connection to Event Hub...")
    print(f"Creating producer for: {EVENTHUB_NAME}")
    
    producer = EventHubProducerClient.from_connection_string(
        conn_str=EVENTHUB_CONNECTION_STRING,
        eventhub_name=EVENTHUB_NAME
    )
    
    print("✓ Producer created successfully")
    
    # Try to get properties
    print("\nAttempting to get Event Hub properties...")
    try:
        props = producer.get_eventhub_properties()
        print("✓ Successfully connected to Event Hub!")
        print(f"\nEvent Hub Details:")
        
        if hasattr(props, 'name'):
            print(f"  - Name: {props.name}")
        elif isinstance(props, dict) and 'name' in props:
            print(f"  - Name: {props['name']}")
            
        if hasattr(props, 'partition_ids'):
            print(f"  - Partitions: {len(props.partition_ids)}")
        elif isinstance(props, dict) and 'partition_ids' in props:
            print(f"  - Partitions: {len(props['partition_ids'])}")
            
    except Exception as prop_error:
        print(f"\n⚠️  Could not get properties: {prop_error}")
        print("\nTrying to send a test event instead...")
        
        # Try sending
        from azure.eventhub import EventData
        batch = producer.create_batch()
        batch.add(EventData(b'{"test": "verification"}'))
        producer.send_batch(batch)
        print("✓ Test event sent successfully!")
        print("\n✓✓✓ Event Hub is accessible and working!")
    
    producer.close()
    
    print("\n" + "=" * 70)
    print("SUCCESS: Configuration is correct!")
    print("=" * 70)
    print(f"\nYour Event Hub '{EVENTHUB_NAME}' exists and is accessible.")
    print("The CBS Token error must be coming from something else.")
    print("\nCheck:")
    print("1. Are you using the EXACT same connection string in Azure Web App?")
    print("2. Are there any extra spaces or quotes in Azure Portal settings?")
    print("3. Try deleting and re-adding the setting in Azure Portal")
    
except Exception as e:
    print(f"\n❌ ERROR: {type(e).__name__}: {e}")
    print("\n" + "=" * 70)
    print("DIAGNOSIS:")
    print("=" * 70)
    
    error_msg = str(e).lower()
    
    if 'cbs token' in error_msg or 'unauthorized' in error_msg:
        print(f"\n❌ Event Hub '{EVENTHUB_NAME}' may not exist in this namespace!")
        print("\nTo check what Event Hubs exist, run:")
        print(f"\n  az eventhubs eventhub list \\")
        print(f"      --resource-group <your-resource-group> \\")
        print(f"      --namespace-name ag-cla-tst-ehub-01 \\")
        print(f"      --output table")
        print("\nOR get the correct Event Hub-level connection string:")
        print(f"\n  az eventhubs eventhub authorization-rule keys list \\")
        print(f"      --resource-group <your-resource-group> \\")
        print(f"      --namespace-name ag-cla-tst-ehub-01 \\")
        print(f"      --eventhub-name {EVENTHUB_NAME} \\")
        print(f"      --name RootManageSharedAccessKey \\")
        print(f"      --query primaryConnectionString")
        print("\nThis will give you a connection string WITH EntityPath,")
        print("which eliminates the need for EVENTHUB_NAME variable.")
        
    elif 'not found' in error_msg or 'does not exist' in error_msg:
        print(f"\n❌ Event Hub '{EVENTHUB_NAME}' does not exist!")
        print("\nDouble-check the name - it's case-sensitive.")
        print("List available Event Hubs with:")
        print(f"\n  az eventhubs eventhub list \\")
        print(f"      --resource-group <your-resource-group> \\")
        print(f"      --namespace-name ag-cla-tst-ehub-01 \\")
        print(f"      --output table")
    
    else:
        print(f"\nUnexpected error: {e}")
        print("\nTry:")
        print("1. Verify Event Hub exists in Azure Portal")
        print("2. Check the Shared Access Policy has 'Send' permission")
        print("3. Get Event Hub-level connection string (with EntityPath)")
    
    sys.exit(1)
