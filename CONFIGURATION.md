# Configuration Guide for Event Hub Ingestion

This application receives HTTP POST requests with compressed data and forwards them to Azure Event Hub.

## Environment Variables

### Required Configuration (Choose one authentication method)

#### Option 1: Connection String Authentication (Simpler for development)
```bash
EVENTHUB_CONNECTION_STRING="Endpoint=sb://yournamespace.servicebus.windows.net/;SharedAccessKeyName=yourpolicy;SharedAccessKey=yourkey"
EVENTHUB_NAME="your-eventhub-name"
```

#### Option 2: Managed Identity Authentication (Recommended for production)
```bash
EVENTHUB_FULLY_QUALIFIED_NAMESPACE="yournamespace.servicebus.windows.net"
EVENTHUB_NAME="your-eventhub-name"
```

### Optional HTTP Authentication
```bash
BASIC_AUTH_USERNAME="admin"  # Default: admin
BASIC_AUTH_PASSWORD="password"  # Default: password
```

## Azure Event Hub Setup

### 1. Create an Event Hub Namespace and Event Hub

```bash
# Create resource group (if needed)
az group create --name myResourceGroup --location eastus

# Create Event Hub namespace
az eventhubs namespace create \
    --resource-group myResourceGroup \
    --name myEventHubNamespace \
    --location eastus \
    --sku Standard

# Create Event Hub
az eventhubs eventhub create \
    --resource-group myResourceGroup \
    --namespace-name myEventHubNamespace \
    --name myEventHub \
    --partition-count 4
```

### 2. Get Connection String (for Option 1)

```bash
az eventhubs namespace authorization-rule keys list \
    --resource-group myResourceGroup \
    --namespace-name myEventHubNamespace \
    --name RootManageSharedAccessKey \
    --query primaryConnectionString \
    --output tsv
```

### 3. Configure Managed Identity (for Option 2)

If running in Azure (App Service, Container Apps, etc.):

```bash
# Enable system-assigned managed identity
az webapp identity assign \
    --name myWebApp \
    --resource-group myResourceGroup

# Get the principal ID
PRINCIPAL_ID=$(az webapp identity show \
    --name myWebApp \
    --resource-group myResourceGroup \
    --query principalId \
    --output tsv)

# Assign "Azure Event Hubs Data Sender" role
az role assignment create \
    --assignee $PRINCIPAL_ID \
    --role "Azure Event Hubs Data Sender" \
    --scope /subscriptions/{subscription-id}/resourceGroups/myResourceGroup/providers/Microsoft.EventHub/namespaces/myEventHubNamespace
```

## Installation

```bash
pip install -r requirements.txt
```

## Running the Application

### Local Development
```bash
# Set environment variables
export EVENTHUB_CONNECTION_STRING="your-connection-string"
export EVENTHUB_NAME="your-eventhub-name"
export BASIC_AUTH_USERNAME="admin"
export BASIC_AUTH_PASSWORD="password"

# Run the app
python app.py
```

### Production (with Gunicorn)
```bash
gunicorn --worker-class gevent --workers 4 --bind 0.0.0.0:8000 app:app
```

## API Usage

### Send Data to Event Hub

**Endpoint:** `POST /`

**Headers:**
- `Authorization: Basic <base64-encoded-credentials>`
- `Log-Type: <optional-log-type>` (will be added as event property)

**Body:** Gzip-compressed JSON data

**Example:**
```bash
# Prepare data
echo '{"message": "test event", "timestamp": "2024-11-07T10:00:00Z"}' | gzip > data.gz

# Send to the service
curl -X POST http://localhost:8000/ \
  -H "Authorization: Basic $(echo -n 'admin:password' | base64)" \
  -H "Log-Type: TestLog" \
  --data-binary @data.gz
```

### Health Check

**Endpoint:** `GET /health`

**Response:** `{"success": true}`

## Security Best Practices

1. **Use Managed Identity** in production environments (Azure App Service, Container Apps, AKS)
2. **Store secrets securely** using Azure Key Vault
3. **Use strong passwords** for Basic Auth credentials
4. **Enable HTTPS** in production
5. **Assign minimal RBAC roles** (Azure Event Hubs Data Sender is sufficient for sending)

## Troubleshooting

### Authentication Errors
- Verify Event Hub connection string or namespace is correct
- Check Managed Identity has "Azure Event Hubs Data Sender" role
- Ensure Event Hub name is correct

### Import Errors
- Run `pip install -r requirements.txt` to install dependencies

### Connection Issues
- Check network connectivity to Event Hub namespace
- Verify firewall rules allow outbound connections to `*.servicebus.windows.net` on port 5671 (AMQP) or 443 (AMQP over WebSocket)

## Migration from Azure Sentinel

This application was migrated from forwarding to Azure Sentinel to Azure Event Hub. Key changes:

1. **Authentication:** Changed from Sentinel workspace ID/shared key to Event Hub connection string or Managed Identity
2. **Endpoint:** Data now goes to Event Hub instead of Log Analytics API
3. **Batching:** Event Hub client handles efficient batching automatically
4. **Properties:** Log-Type header is preserved as an event property
5. **Compression:** Still accepts gzip-compressed payloads

## Next Steps

After data reaches Event Hub, you can:
- Process events using Azure Stream Analytics
- Consume events with Azure Functions
- Forward to Azure Data Explorer (Kusto)
- Store in Azure Data Lake or Blob Storage
- Process with custom consumer applications
