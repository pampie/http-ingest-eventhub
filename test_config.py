"""
Diagnostic script to test Event Hub configuration
Run this to verify your environment variables are set correctly
"""
import os
import sys

print("=" * 60)
print("Event Hub Configuration Diagnostics")
print("=" * 60)

# Check environment variables
eventhub_name = os.environ.get('EVENTHUB_NAME')
eventhub_connection_string = os.environ.get('EVENTHUB_CONNECTION_STRING')
eventhub_namespace = os.environ.get('EVENTHUB_FULLY_QUALIFIED_NAMESPACE')

print(f"\n1. EVENTHUB_NAME: {eventhub_name if eventhub_name else '❌ NOT SET'}")
print(f"2. EVENTHUB_CONNECTION_STRING: {'✓ SET' if eventhub_connection_string else '❌ NOT SET'}")
if eventhub_connection_string:
    # Show first/last few characters to verify
    conn_str_preview = f"{eventhub_connection_string[:30]}...{eventhub_connection_string[-10:]}" if len(eventhub_connection_string) > 50 else eventhub_connection_string
    print(f"   Preview: {conn_str_preview}")
    # Check for EntityPath
    has_entity_path = 'EntityPath=' in eventhub_connection_string
    print(f"   Contains EntityPath: {'✓ YES' if has_entity_path else '❌ NO'}")
    if has_entity_path:
        # Extract EntityPath value
        import re
        entity_match = re.search(r'EntityPath=([^;]+)', eventhub_connection_string)
        if entity_match:
            print(f"   EntityPath value: {entity_match.group(1)}")
print(f"3. EVENTHUB_FULLY_QUALIFIED_NAMESPACE: {eventhub_namespace if eventhub_namespace else '❌ NOT SET'}")

print("\n" + "=" * 60)
print("Configuration Analysis")
print("=" * 60)

if eventhub_connection_string and eventhub_name:
    print("✓ Connection String mode detected")
    print("  - Will use connection string authentication")
    print("  - This is simpler and recommended for testing")
elif eventhub_namespace and eventhub_name:
    print("✓ Managed Identity mode detected")
    print("  - Will use DefaultAzureCredential")
    print("  - Requires App Service Managed Identity enabled")
    print("  - Requires 'Azure Event Hubs Data Sender' role assigned")
else:
    print("❌ CONFIGURATION ERROR:")
    if not eventhub_name:
        print("  - EVENTHUB_NAME is not set")
    print("  - Need either:")
    print("    Option A: EVENTHUB_CONNECTION_STRING + EVENTHUB_NAME")
    print("    Option B: EVENTHUB_FULLY_QUALIFIED_NAMESPACE + EVENTHUB_NAME")
    sys.exit(1)

print("\n" + "=" * 60)
print("Testing Event Hub Connection")
print("=" * 60)

try:
    from azure.eventhub import EventHubProducerClient, EventData
    from azure.identity import DefaultAzureCredential
    
    print("\n✓ Azure SDK packages imported successfully")
    
    if eventhub_connection_string:
        print("\nAttempting to create producer with connection string...")
        
        # Check if EntityPath is in connection string
        if 'EntityPath=' in eventhub_connection_string:
            print("Connection string contains EntityPath, using it directly...")
            producer = EventHubProducerClient.from_connection_string(
                conn_str=eventhub_connection_string
            )
        elif eventhub_name:
            print(f"Using EVENTHUB_NAME parameter: {eventhub_name}")
            producer = EventHubProducerClient.from_connection_string(
                conn_str=eventhub_connection_string,
                eventhub_name=eventhub_name
            )
        else:
            print("❌ ERROR: Connection string doesn't have EntityPath and EVENTHUB_NAME is not set")
            sys.exit(1)
            
        print("✓ Producer client created successfully")
        
        # Try to get properties (this validates the connection)
        print("\nValidating connection by getting Event Hub properties...")
        try:
            props = producer.get_eventhub_properties()
            print(f"✓ Connection validated!")
            
            # Try different ways to get the Event Hub name
            eventhub_actual_name = None
            if hasattr(props, 'name'):
                eventhub_actual_name = props.name
            elif isinstance(props, dict) and 'name' in props:
                eventhub_actual_name = props['name']
            
            if eventhub_actual_name:
                print(f"  - Event Hub Name: {eventhub_actual_name}")
            else:
                # Extract from connection string or use parameter
                if 'EntityPath=' in eventhub_connection_string:
                    import re
                    entity_match = re.search(r'EntityPath=([^;]+)', eventhub_connection_string)
                    if entity_match:
                        print(f"  - Event Hub Name: {entity_match.group(1)} (from EntityPath)")
                elif eventhub_name:
                    print(f"  - Event Hub Name: {eventhub_name} (from parameter)")
            
            # Try to get partition info
            if hasattr(props, 'partition_ids'):
                print(f"  - Partition Count: {len(props.partition_ids)}")
                print(f"  - Partition IDs: {list(props.partition_ids)}")
            elif isinstance(props, dict) and 'partition_ids' in props:
                print(f"  - Partition Count: {len(props['partition_ids'])}")
                print(f"  - Partition IDs: {props['partition_ids']}")
                
        except Exception as prop_error:
            print(f"⚠ Could not get properties (but connection might still work): {prop_error}")
            print("  Attempting to send a test event instead...")
            
            # Try sending a test event
            from azure.eventhub import EventData
            test_batch = producer.create_batch()
            test_event = EventData(b'{"test": "connection validation"}')
            test_batch.add(test_event)
            producer.send_batch(test_batch)
            print("✓ Test event sent successfully!")
        
        producer.close()
        print("\n✓✓✓ ALL TESTS PASSED ✓✓✓")
        print("\nYour configuration is correct and Event Hub is accessible!")
        
    else:
        print("\nAttempting to create producer with Managed Identity...")
        credential = DefaultAzureCredential()
        producer = EventHubProducerClient(
            fully_qualified_namespace=eventhub_namespace,
            eventhub_name=eventhub_name,
            credential=credential
        )
        print("✓ Producer client created successfully")
        
        # Try to get properties (this validates the connection)
        print("\nValidating connection by getting Event Hub properties...")
        try:
            props = producer.get_eventhub_properties()
            print(f"✓ Connection validated!")
            
            # Try different ways to get the Event Hub name
            eventhub_actual_name = None
            if hasattr(props, 'name'):
                eventhub_actual_name = props.name
            elif isinstance(props, dict) and 'name' in props:
                eventhub_actual_name = props['name']
            
            if eventhub_actual_name:
                print(f"  - Event Hub Name: {eventhub_actual_name}")
            else:
                # Use parameter for display
                if eventhub_name:
                    print(f"  - Event Hub Name: {eventhub_name} (from parameter)")
            
            # Try to get partition info
            if hasattr(props, 'partition_ids'):
                print(f"  - Partition Count: {len(props.partition_ids)}")
                print(f"  - Partition IDs: {list(props.partition_ids)}")
            elif isinstance(props, dict) and 'partition_ids' in props:
                print(f"  - Partition Count: {len(props['partition_ids'])}")
                print(f"  - Partition IDs: {props['partition_ids']}")
                
        except Exception as prop_error:
            print(f"⚠ Could not get properties (but connection might still work): {prop_error}")
            print("  Attempting to send a test event instead...")
            
            # Try sending a test event
            from azure.eventhub import EventData
            test_batch = producer.create_batch()
            test_event = EventData(b'{"test": "connection validation"}')
            test_batch.add(test_event)
            producer.send_batch(test_batch)
            print("✓ Test event sent successfully!")
        
        producer.close()
        print("\n✓✓✓ ALL TESTS PASSED ✓✓✓")
        print("\nYour configuration is correct and Event Hub is accessible!")
        
except ImportError as e:
    print(f"\n❌ ERROR: Missing required packages")
    print(f"   {e}")
    print("\n   Run: pip install -r requirements.txt")
    sys.exit(1)
    
except Exception as e:
    print(f"\n❌ ERROR: Failed to connect to Event Hub")
    print(f"   {type(e).__name__}: {e}")
    print("\n   Common issues:")
    print("   1. Connection string is invalid or incomplete")
    print("   2. Event Hub name doesn't match")
    print("   3. Network connectivity issues")
    print("   4. For Managed Identity: identity not enabled or role not assigned")
    sys.exit(1)

print("\n" + "=" * 60)
