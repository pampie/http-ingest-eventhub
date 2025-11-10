from flask import Flask, request
from azure.eventhub import EventHubProducerClient, EventData
from azure.identity import DefaultAzureCredential

import base64
import gzip
import json
import logging
import os
import sys


# Configure logging BEFORE any other code
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    stream=sys.stdout
)
logger = logging.getLogger(__name__)

app = Flask(__name__)


# Event Hub Configuration - Clean and strip environment variables
EVENTHUB_FULLY_QUALIFIED_NAMESPACE = os.environ.get('EVENTHUB_FULLY_QUALIFIED_NAMESPACE', '').strip().strip('"').strip("'")  # e.g., 'yournamespace.servicebus.windows.net'
EVENTHUB_NAME = os.environ.get('EVENTHUB_NAME', '').strip().strip('"').strip("'")
EVENTHUB_CONNECTION_STRING = os.environ.get('EVENTHUB_CONNECTION_STRING', '').strip().strip('"').strip("'")  # Optional: for connection string auth

# Clean empty strings to None
EVENTHUB_FULLY_QUALIFIED_NAMESPACE = EVENTHUB_FULLY_QUALIFIED_NAMESPACE if EVENTHUB_FULLY_QUALIFIED_NAMESPACE else None
EVENTHUB_NAME = EVENTHUB_NAME if EVENTHUB_NAME else None
EVENTHUB_CONNECTION_STRING = EVENTHUB_CONNECTION_STRING if EVENTHUB_CONNECTION_STRING else None

# Basic Auth credentials for the HTTP endpoint
BASIC_AUTH_USERNAME = os.environ.get('BASIC_AUTH_USERNAME', 'admin').strip()
BASIC_AUTH_PASSWORD = os.environ.get('BASIC_AUTH_PASSWORD', 'password').strip()

# Debug: Print configuration (without exposing full secrets)
logger.info("=== Event Hub Configuration ===")
logger.info(f"EVENTHUB_NAME: {EVENTHUB_NAME}")
logger.info(f"EVENTHUB_NAME type: {type(EVENTHUB_NAME)}")
logger.info(f"EVENTHUB_CONNECTION_STRING present: {bool(EVENTHUB_CONNECTION_STRING)}")

# Log raw environment variable to detect Azure Portal issues
raw_conn_str = os.environ.get('EVENTHUB_CONNECTION_STRING', '')
if raw_conn_str:
    logger.info(f"Raw connection string length (before cleaning): {len(raw_conn_str)} chars")
    logger.info(f"Cleaned connection string length (after cleaning): {len(EVENTHUB_CONNECTION_STRING)} chars" if EVENTHUB_CONNECTION_STRING else "Cleaned to None/empty")
    
    # Check for common Azure Portal issues
    if raw_conn_str.startswith('"') or raw_conn_str.startswith("'"):
        logger.warning("⚠️  Raw connection string starts with quote character!")
    if raw_conn_str != EVENTHUB_CONNECTION_STRING:
        logger.info(f"✓ Connection string was cleaned (removed {len(raw_conn_str) - (len(EVENTHUB_CONNECTION_STRING) if EVENTHUB_CONNECTION_STRING else 0)} characters)")

if EVENTHUB_CONNECTION_STRING:
    # Check if EntityPath is in connection string
    has_entity_path = 'EntityPath=' in EVENTHUB_CONNECTION_STRING
    logger.info(f"Connection string contains EntityPath: {has_entity_path}")
    logger.info(f"Connection string length: {len(EVENTHUB_CONNECTION_STRING)} characters")
    
    # Check for minimum expected length
    if len(EVENTHUB_CONNECTION_STRING) < 150:
        logger.warning(f"⚠️  Connection string seems too short ({len(EVENTHUB_CONNECTION_STRING)} chars). Expected 200-300 chars.")
        logger.warning("⚠️  It may be truncated or incomplete!")
    
    # Extract and validate EntityPath
    if has_entity_path:
        import re
        entity_match = re.search(r'EntityPath=([^;]+)', EVENTHUB_CONNECTION_STRING)
        if entity_match:
            entity_path_value = entity_match.group(1)
            logger.info(f"EntityPath in connection string: {entity_path_value}")
            if EVENTHUB_NAME and EVENTHUB_NAME != entity_path_value:
                logger.warning(f"⚠️  MISMATCH: EVENTHUB_NAME ({EVENTHUB_NAME}) differs from EntityPath ({entity_path_value})")
                logger.warning(f"⚠️  This will cause 'CBS Token authentication failed' error!")
                logger.warning(f"⚠️  SOLUTION: Remove EVENTHUB_NAME variable from Azure Web App config")
    else:
        if not EVENTHUB_NAME:
            logger.error("❌ Connection string has no EntityPath AND EVENTHUB_NAME is not set!")
        else:
            logger.info(f"✓ Will use EVENTHUB_NAME parameter: {EVENTHUB_NAME}")
    
    # Show first 50 and last 20 chars for verification (without exposing full key)
    if len(EVENTHUB_CONNECTION_STRING) > 100:
        preview = f"{EVENTHUB_CONNECTION_STRING[:50]}...{EVENTHUB_CONNECTION_STRING[-20:]}"
        logger.info(f"Connection string preview: {preview}")
    else:
        # If too short, show more to help diagnose
        preview = f"{EVENTHUB_CONNECTION_STRING[:80]}..." if len(EVENTHUB_CONNECTION_STRING) > 80 else EVENTHUB_CONNECTION_STRING
        logger.warning(f"⚠️  Short connection string: {preview}")
    
    # Check if connection string looks correct
    required_parts = ['Endpoint=', 'SharedAccessKeyName=', 'SharedAccessKey=']
    missing_parts = [part for part in required_parts if part not in EVENTHUB_CONNECTION_STRING]
    if missing_parts:
        logger.error(f"❌ Connection string missing required parts: {missing_parts}")
        logger.error(f"❌ This will cause authentication to fail!")
    else:
        logger.info("✓ Connection string contains all required parts")
else:
    logger.error("❌ EVENTHUB_CONNECTION_STRING is empty or None after cleaning!")
        
logger.info(f"EVENTHUB_FULLY_QUALIFIED_NAMESPACE: {EVENTHUB_FULLY_QUALIFIED_NAMESPACE}")

# Validate and initialize Event Hub producer
producer_client = None
try:
    # Check if running in Azure with Managed Identity environment variables
    msi_endpoint = os.environ.get('MSI_ENDPOINT')
    msi_secret = os.environ.get('MSI_SECRET')
    identity_endpoint = os.environ.get('IDENTITY_ENDPOINT')
    identity_header = os.environ.get('IDENTITY_HEADER')
    
    if msi_endpoint or identity_endpoint:
        logger.info("⚠️  Detected Azure Managed Identity environment variables:")
        if msi_endpoint:
            logger.info(f"   MSI_ENDPOINT: {msi_endpoint}")
        if identity_endpoint:
            logger.info(f"   IDENTITY_ENDPOINT: {identity_endpoint}")
        logger.warning("⚠️  These may interfere with connection string authentication!")
        logger.info("   Forcing connection string authentication...")
    
    if EVENTHUB_CONNECTION_STRING:
        # Using connection string authentication
        logger.info("Initializing Event Hub producer with connection string...")
        
        # Check if EntityPath is already in the connection string
        if 'EntityPath=' in EVENTHUB_CONNECTION_STRING:
            # EntityPath is in connection string, don't pass eventhub_name
            logger.info("EntityPath found in connection string, using it directly")
            producer_client = EventHubProducerClient.from_connection_string(
                conn_str=EVENTHUB_CONNECTION_STRING,
                # Important: Don't pass any credential parameter when using connection string
                # This ensures it uses the SharedAccessKey from the connection string
            )
        elif EVENTHUB_NAME:
            # EntityPath not in connection string, use eventhub_name parameter
            logger.info(f"Using EVENTHUB_NAME parameter: {EVENTHUB_NAME}")
            producer_client = EventHubProducerClient.from_connection_string(
                conn_str=EVENTHUB_CONNECTION_STRING,
                eventhub_name=EVENTHUB_NAME,
                # Important: Don't pass any credential parameter
            )
        else:
            error_msg = "Connection string doesn't contain EntityPath and EVENTHUB_NAME is not set"
            logger.error(error_msg)
            raise Exception(error_msg)
        
        logger.info("✓ Event Hub producer initialized successfully with connection string")
        logger.info("✓ Using SharedAccessKey authentication (not Managed Identity)")
        
    elif EVENTHUB_FULLY_QUALIFIED_NAMESPACE and EVENTHUB_NAME:
        # Using Managed Identity / DefaultAzureCredential (recommended for production)
        logger.info("Initializing Event Hub producer with Managed Identity...")
        credential = DefaultAzureCredential()
        producer_client = EventHubProducerClient(
            fully_qualified_namespace=EVENTHUB_FULLY_QUALIFIED_NAMESPACE,
            eventhub_name=EVENTHUB_NAME,
            credential=credential
        )
        logger.info("✓ Event Hub producer initialized successfully with Managed Identity")
    else:
        error_msg = "Please configure Event Hub connection: either EVENTHUB_CONNECTION_STRING or both EVENTHUB_FULLY_QUALIFIED_NAMESPACE and EVENTHUB_NAME"
        logger.error(error_msg)
        raise Exception(error_msg)
except Exception as init_error:
    logger.error(f"Failed to initialize Event Hub producer: {init_error}")
    raise

BASIC_AUTH = base64.b64encode("{}:{}".format(BASIC_AUTH_USERNAME, BASIC_AUTH_PASSWORD).encode()).decode("utf-8")
LOG_TYPE = 'Log-Type'
FAILURE_RESPONSE = json.dumps({'success':False})
SUCCESS_RESPONSE = json.dumps({'success':True})
APPLICATION_JSON = {'ContentType':'application/json'}


class UnAuthorizedException(Exception):
    pass


class ProcessingException(Exception):
    pass


def send_to_eventhub(data, log_type=None):
    """
    Send data to Azure Event Hub with retry logic
    
    Args:
        data: The event data to send (bytes or string)
        log_type: Optional log type for event properties
    
    Raises:
        ProcessingException: If sending fails
    """
    if producer_client is None:
        error_msg = "Event Hub producer client is not initialized"
        logger.error(error_msg)
        raise ProcessingException(error_msg)
    
    try:
        logger.debug("Creating event batch...")
        # Create event data batch
        event_data_batch = producer_client.create_batch()
        
        logger.debug("Creating event data...")
        # Create event with the data
        event = EventData(data)
        
        # Add log type as event property if provided
        if log_type:
            event.properties['LogType'] = log_type
            logger.debug(f"Added LogType property: {log_type}")
        
        # Add event to batch
        logger.debug("Adding event to batch...")
        event_data_batch.add(event)
        
        # Send the batch to Event Hub
        logger.info(f"Sending batch to Event Hub (size: {len(data)} bytes)...")
        producer_client.send_batch(event_data_batch)
        logger.info(f"✓ Successfully sent event to Event Hub. Log Type: {log_type}")
        
    except Exception as e:
        error_msg = f"Failed to send event to Event Hub: {type(e).__name__}: {str(e)}"
        logger.error(error_msg)
        logger.exception("Full exception details:")
        raise ProcessingException(error_msg)


@app.route('/', methods=['POST'])
def func():
    """
    HTTP endpoint that receives compressed data, decompresses it, and forwards to Event Hub.
    Expects Basic authentication in the Authorization header.
    """
    try:
        # Extract authorization header
        auth_header = request.headers.get("authorization")
        if not auth_header:
            logger.error("Missing authorization header")
            raise UnAuthorizedException()
        
        # Verify Basic authentication
        if "Basic" in auth_header:
            basic_auth_value = auth_header.replace("Basic ", "").strip()
            if basic_auth_value != BASIC_AUTH:
                logger.error("Unauthorized: Basic auth mismatch")
                raise UnAuthorizedException()
        else:
            logger.error("Unauthorized: Basic auth not found")
            raise UnAuthorizedException()
        
        # Get the log type from headers (optional)
        log_type = request.headers.get(LOG_TYPE)
        
        # Get request body
        body = request.get_data()
        
        # Decompress payload
        try:
            decompressed = gzip.decompress(body)
            logger.debug(f"Decompressed data: {len(decompressed)} bytes")
        except Exception as decompress_error:
            logger.error(f"Failed to decompress data: {decompress_error}")
            # If decompression fails, try to use the body as-is
            if len(body) == 0:
                logger.error("Empty body received")
                return FAILURE_RESPONSE, 400, APPLICATION_JSON
            decompressed = body
        
        decomp_body_length = len(decompressed)
        if decomp_body_length == 0:
            logger.error("Decompressed body is empty")
            return FAILURE_RESPONSE, 400, APPLICATION_JSON
        
        # Send to Event Hub
        send_to_eventhub(decompressed, log_type)
        logger.info(f"Successfully forwarded {decomp_body_length} bytes to Event Hub")
        
    except UnAuthorizedException:
        return FAILURE_RESPONSE, 401, APPLICATION_JSON
    except ProcessingException as e:
        logger.error(f"Processing error: {e}")
        return FAILURE_RESPONSE, 500, APPLICATION_JSON
    except Exception as e:
        logger.error(f"Unexpected error: {e}")
        return FAILURE_RESPONSE, 500, APPLICATION_JSON
       
    return SUCCESS_RESPONSE, 200, APPLICATION_JSON 


@app.route('/health', methods=['GET'])
def health():
    return SUCCESS_RESPONSE, 200, APPLICATION_JSON


@app.route('/config-check', methods=['GET'])
def config_check():
    """
    Diagnostic endpoint to check Event Hub configuration
    Access at: https://your-webapp.azurewebsites.net/config-check
    """
    import re
    
    diagnostic_info = {
        "eventhub_name": EVENTHUB_NAME,
        "eventhub_name_set": EVENTHUB_NAME is not None,
        "connection_string_set": EVENTHUB_CONNECTION_STRING is not None,
        "connection_string_length": len(EVENTHUB_CONNECTION_STRING) if EVENTHUB_CONNECTION_STRING else 0,
    }
    
    # Check for Azure Managed Identity environment variables
    msi_endpoint = os.environ.get('MSI_ENDPOINT')
    msi_secret = os.environ.get('MSI_SECRET')
    identity_endpoint = os.environ.get('IDENTITY_ENDPOINT')
    identity_header = os.environ.get('IDENTITY_HEADER')
    
    has_managed_identity_env = bool(msi_endpoint or identity_endpoint)
    diagnostic_info['azure_managed_identity_detected'] = has_managed_identity_env
    
    if has_managed_identity_env:
        diagnostic_info['managed_identity_env_vars'] = {
            'MSI_ENDPOINT': bool(msi_endpoint),
            'MSI_SECRET': bool(msi_secret),
            'IDENTITY_ENDPOINT': bool(identity_endpoint),
            'IDENTITY_HEADER': bool(identity_header)
        }
        diagnostic_info['managed_identity_warning'] = "Azure Managed Identity detected - may interfere with connection string authentication!"
    
    if EVENTHUB_CONNECTION_STRING:
        # Check for required parts
        required_parts = {
            'has_endpoint': 'Endpoint=' in EVENTHUB_CONNECTION_STRING,
            'has_keyname': 'SharedAccessKeyName=' in EVENTHUB_CONNECTION_STRING,
            'has_key': 'SharedAccessKey=' in EVENTHUB_CONNECTION_STRING,
            'has_entity_path': 'EntityPath=' in EVENTHUB_CONNECTION_STRING,
        }
        diagnostic_info.update(required_parts)
        
        # Extract EntityPath if present
        if required_parts['has_entity_path']:
            entity_match = re.search(r'EntityPath=([^;]+)', EVENTHUB_CONNECTION_STRING)
            if entity_match:
                entity_path_value = entity_match.group(1)
                diagnostic_info['entity_path_value'] = entity_path_value
                diagnostic_info['name_matches_entity_path'] = (EVENTHUB_NAME == entity_path_value) if EVENTHUB_NAME else None
        
        # Preview (safe)
        if len(EVENTHUB_CONNECTION_STRING) > 100:
            diagnostic_info['connection_string_preview'] = f"{EVENTHUB_CONNECTION_STRING[:50]}...{EVENTHUB_CONNECTION_STRING[-20:]}"
        
        # Check length
        if len(EVENTHUB_CONNECTION_STRING) < 150:
            diagnostic_info['warning'] = f"Connection string seems too short ({len(EVENTHUB_CONNECTION_STRING)} chars). May be truncated!"
    
    # Determine if configuration is valid
    is_valid = (
        EVENTHUB_CONNECTION_STRING and
        'Endpoint=' in EVENTHUB_CONNECTION_STRING and
        'SharedAccessKeyName=' in EVENTHUB_CONNECTION_STRING and
        'SharedAccessKey=' in EVENTHUB_CONNECTION_STRING and
        len(EVENTHUB_CONNECTION_STRING) > 150
    )
    
    diagnostic_info['configuration_valid'] = is_valid
    diagnostic_info['producer_initialized'] = producer_client is not None
    
    if not is_valid:
        diagnostic_info['errors'] = []
        if not EVENTHUB_CONNECTION_STRING:
            diagnostic_info['errors'].append("EVENTHUB_CONNECTION_STRING not set")
        elif len(EVENTHUB_CONNECTION_STRING) < 150:
            diagnostic_info['errors'].append("Connection string too short - likely truncated")
        if EVENTHUB_CONNECTION_STRING and 'SharedAccessKey=' not in EVENTHUB_CONNECTION_STRING:
            diagnostic_info['errors'].append("Missing SharedAccessKey in connection string")
    
    return json.dumps(diagnostic_info, indent=2), 200, {'ContentType': 'application/json'} 


def cleanup():
    """Close Event Hub producer client on application shutdown"""
    try:
        if producer_client:
            producer_client.close()
            logger.info("Event Hub producer client closed")
    except Exception as e:
        logger.error(f"Error closing Event Hub producer: {e}")


if __name__ == '__main__':
    import atexit
    atexit.register(cleanup)
    app.run()