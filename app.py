from flask import Flask, request
from azure.eventhub import EventHubProducerClient, EventData
from azure.identity import DefaultAzureCredential

import base64
import gzip
import json
import logging
import os 


app = Flask(__name__)


# Event Hub Configuration
EVENTHUB_FULLY_QUALIFIED_NAMESPACE = os.environ.get('EVENTHUB_FULLY_QUALIFIED_NAMESPACE')  # e.g., 'yournamespace.servicebus.windows.net'
EVENTHUB_NAME = os.environ.get('EVENTHUB_NAME')
EVENTHUB_CONNECTION_STRING = os.environ.get('EVENTHUB_CONNECTION_STRING')  # Optional: for connection string auth

# Basic Auth credentials for the HTTP endpoint
BASIC_AUTH_USERNAME = os.environ.get('BASIC_AUTH_USERNAME', 'admin')
BASIC_AUTH_PASSWORD = os.environ.get('BASIC_AUTH_PASSWORD', 'password')

# Validate configuration
if EVENTHUB_CONNECTION_STRING:
    # Using connection string authentication
    producer_client = EventHubProducerClient.from_connection_string(
        conn_str=EVENTHUB_CONNECTION_STRING,
        eventhub_name=EVENTHUB_NAME
    )
    logging.info("Event Hub producer initialized with connection string")
elif EVENTHUB_FULLY_QUALIFIED_NAMESPACE and EVENTHUB_NAME:
    # Using Managed Identity / DefaultAzureCredential (recommended for production)
    credential = DefaultAzureCredential()
    producer_client = EventHubProducerClient(
        fully_qualified_namespace=EVENTHUB_FULLY_QUALIFIED_NAMESPACE,
        eventhub_name=EVENTHUB_NAME,
        credential=credential
    )
    logging.info("Event Hub producer initialized with Managed Identity")
else:
    raise Exception("Please configure Event Hub connection: either EVENTHUB_CONNECTION_STRING or both EVENTHUB_FULLY_QUALIFIED_NAMESPACE and EVENTHUB_NAME")

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
    try:
        # Create event data batch
        event_data_batch = producer_client.create_batch()
        
        # Create event with the data
        event = EventData(data)
        
        # Add log type as event property if provided
        if log_type:
            event.properties['LogType'] = log_type
        
        # Add event to batch
        event_data_batch.add(event)
        
        # Send the batch to Event Hub
        producer_client.send_batch(event_data_batch)
        logging.debug(f"Successfully sent event to Event Hub. Log Type: {log_type}")
        
    except Exception as e:
        error_msg = f"Failed to send event to Event Hub: {str(e)}"
        logging.error(error_msg)
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
            logging.error("Missing authorization header")
            raise UnAuthorizedException()
        
        # Verify Basic authentication
        if "Basic" in auth_header:
            basic_auth_value = auth_header.replace("Basic ", "").strip()
            if basic_auth_value != BASIC_AUTH:
                logging.error("Unauthorized: Basic auth mismatch")
                raise UnAuthorizedException()
        else:
            logging.error("Unauthorized: Basic auth not found")
            raise UnAuthorizedException()
        
        # Get the log type from headers (optional)
        log_type = request.headers.get(LOG_TYPE)
        
        # Get request body
        body = request.get_data()
        
        # Decompress payload
        try:
            decompressed = gzip.decompress(body)
            logging.debug(f"Decompressed data: {len(decompressed)} bytes")
        except Exception as decompress_error:
            logging.error(f"Failed to decompress data: {decompress_error}")
            # If decompression fails, try to use the body as-is
            if len(body) == 0:
                logging.error("Empty body received")
                return FAILURE_RESPONSE, 400, APPLICATION_JSON
            decompressed = body
        
        decomp_body_length = len(decompressed)
        if decomp_body_length == 0:
            logging.error("Decompressed body is empty")
            return FAILURE_RESPONSE, 400, APPLICATION_JSON
        
        # Send to Event Hub
        send_to_eventhub(decompressed, log_type)
        logging.info(f"Successfully forwarded {decomp_body_length} bytes to Event Hub")
        
    except UnAuthorizedException:
        return FAILURE_RESPONSE, 401, APPLICATION_JSON
    except ProcessingException as e:
        logging.error(f"Processing error: {e}")
        return FAILURE_RESPONSE, 500, APPLICATION_JSON
    except Exception as e:
        logging.error(f"Unexpected error: {e}")
        return FAILURE_RESPONSE, 500, APPLICATION_JSON
       
    return SUCCESS_RESPONSE, 200, APPLICATION_JSON 


@app.route('/health', methods=['GET'])
def health():
    return SUCCESS_RESPONSE, 200, APPLICATION_JSON 


def cleanup():
    """Close Event Hub producer client on application shutdown"""
    try:
        producer_client.close()
        logging.info("Event Hub producer client closed")
    except Exception as e:
        logging.error(f"Error closing Event Hub producer: {e}")


if __name__ == '__main__':
    import atexit
    atexit.register(cleanup)
    app.run()