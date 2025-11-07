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


# Event Hub Configuration
EVENTHUB_FULLY_QUALIFIED_NAMESPACE = os.environ.get('EVENTHUB_FULLY_QUALIFIED_NAMESPACE')  # e.g., 'yournamespace.servicebus.windows.net'
EVENTHUB_NAME = os.environ.get('EVENTHUB_NAME')
EVENTHUB_CONNECTION_STRING = os.environ.get('EVENTHUB_CONNECTION_STRING')  # Optional: for connection string auth

# Basic Auth credentials for the HTTP endpoint
BASIC_AUTH_USERNAME = os.environ.get('BASIC_AUTH_USERNAME', 'admin')
BASIC_AUTH_PASSWORD = os.environ.get('BASIC_AUTH_PASSWORD', 'password')

# Debug: Print configuration (without exposing full secrets)
logger.info("=== Event Hub Configuration ===")
logger.info(f"EVENTHUB_NAME: {EVENTHUB_NAME}")
logger.info(f"EVENTHUB_CONNECTION_STRING present: {bool(EVENTHUB_CONNECTION_STRING)}")
if EVENTHUB_CONNECTION_STRING:
    # Check if EntityPath is in connection string
    has_entity_path = 'EntityPath=' in EVENTHUB_CONNECTION_STRING
    logger.info(f"Connection string contains EntityPath: {has_entity_path}")
logger.info(f"EVENTHUB_FULLY_QUALIFIED_NAMESPACE: {EVENTHUB_FULLY_QUALIFIED_NAMESPACE}")

# Validate and initialize Event Hub producer
producer_client = None
try:
    if EVENTHUB_CONNECTION_STRING:
        # Using connection string authentication
        logger.info("Initializing Event Hub producer with connection string...")
        
        # Check if EntityPath is already in the connection string
        if 'EntityPath=' in EVENTHUB_CONNECTION_STRING:
            # EntityPath is in connection string, don't pass eventhub_name
            logger.info("EntityPath found in connection string, using it directly")
            producer_client = EventHubProducerClient.from_connection_string(
                conn_str=EVENTHUB_CONNECTION_STRING
            )
        elif EVENTHUB_NAME:
            # EntityPath not in connection string, use eventhub_name parameter
            logger.info(f"Using EVENTHUB_NAME parameter: {EVENTHUB_NAME}")
            producer_client = EventHubProducerClient.from_connection_string(
                conn_str=EVENTHUB_CONNECTION_STRING,
                eventhub_name=EVENTHUB_NAME
            )
        else:
            error_msg = "Connection string doesn't contain EntityPath and EVENTHUB_NAME is not set"
            logger.error(error_msg)
            raise Exception(error_msg)
        
        logger.info("✓ Event Hub producer initialized successfully with connection string")
        
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