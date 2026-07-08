.venv\Scripts\activate


You don't need to go *inside* the Docker container. You just point the AWS CLI at LocalStack's port (`4566`) from your terminal. Here are the common commands:

## Verify Services

```bash
# Set credentials (needed for every command, or export them once)
export AWS_ACCESS_KEY_ID=test
export AWS_SECRET_ACCESS_KEY=test
export AWS_DEFAULT_REGION=us-east-1
```

## DynamoDB

```bash
# List tables
aws --endpoint-url=http://localhost:4566 dynamodb list-tables

# Count all items
aws --endpoint-url=http://localhost:4566 dynamodb scan \
  --table-name FraudDetection --select COUNT

# View a specific customer profile
aws --endpoint-url=http://localhost:4566 dynamodb get-item \
  --table-name FraudDetection \
  --key '{"pk": {"S": "CUST#101010#10000001"}, "sk": {"S": "PROFILE"}}'

# View a beneficiary record
aws --endpoint-url=http://localhost:4566 dynamodb get-item \
  --table-name FraudDetection \
  --key '{"pk": {"S": "BENE#606060#60000001"}, "sk": {"S": "STATUS"}}'

# Scan all items (shows everything)
aws --endpoint-url=http://localhost:4566 dynamodb scan \
  --table-name FraudDetection
```

## S3 (Audit Archive)

```bash
# List buckets
aws --endpoint-url=http://localhost:4566 s3 ls

# List files in the audit bucket
aws --endpoint-url=http://localhost:4566 s3 ls s3://fraud-audit-archive/ --recursive

# Read a specific audit file
aws --endpoint-url=http://localhost:4566 s3 cp \
  s3://fraud-audit-archive/decisions/2026/06/18/some-message-id.json -
```

## EventBridge

```bash
# List event buses
aws --endpoint-url=http://localhost:4566 events list-event-buses

# List rules on the fraud-detection bus
aws --endpoint-url=http://localhost:4566 events list-rules \
  --event-bus-name fraud-detection
```

## SQS

```bash
# List queues
aws --endpoint-url=http://localhost:4566 sqs list-queues
```

## Docker Container Itself

```bash
# Check if LocalStack is running
docker ps

# View LocalStack logs
docker logs localstack

# Go inside the container (rarely needed)
docker exec -it localstack bash
```

## Quick Verification Script

Here's a one-liner to confirm everything is healthy:

```bash
export AWS_ACCESS_KEY_ID=test AWS_SECRET_ACCESS_KEY=test AWS_DEFAULT_REGION=us-east-1

echo "=== Tables ===" && \
aws --endpoint-url=http://localhost:4566 dynamodb list-tables && \
echo "=== Item Count ===" && \
aws --endpoint-url=http://localhost:4566 dynamodb scan --table-name FraudDetection --select COUNT --query 'Count' && \
echo "=== S3 Buckets ===" && \
aws --endpoint-url=http://localhost:4566 s3 ls && \
echo "=== Event Buses ===" && \
aws --endpoint-url=http://localhost:4566 events list-event-buses --query 'EventBuses[].Name'
```

The key takeaway: you never need to enter the Docker container. The AWS CLI on your machine talks to LocalStack over `http://localhost:4566` — the same way the Python backend does with boto3.