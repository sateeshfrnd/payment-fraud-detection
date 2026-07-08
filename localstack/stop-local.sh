#!/bin/bash
###############################################################################
# Payment Fraud Detection (Python) — Local Development Setup
#
# Starts the full local stack:
#   1. Checks prerequisites (Python 3, Docker, AWS CLI, pip packages)
#   2. Starts LocalStack (DynamoDB, S3, EventBridge)
#   3. Deploys AWS resources (DynamoDB table, S3 bucket, EventBridge bus)
#   4. Seeds test data (80 customer profiles + 20 beneficiary records)
#   5. Starts the FastAPI backend (port 8000)
#   6. Starts the Streamlit frontend (port 8501)
#
# Usage:
#   chmod +x payment-fraud-detection/localstack/start-local.sh
#   ./payment-fraud-detection/localstack/start-local.sh
#
# Frontend: http://localhost:8501
# Backend:  http://localhost:8000
# API Docs: http://localhost:8000/docs
#
# To stop:
#   ./payment-fraud-detection/localstack/stop-local.sh
###############################################################################
set -e

# --- Configuration ---
REGION="us-east-1"
ENDPOINT="http://localhost:4566"
TABLE_NAME="FraudDetection"
AUDIT_BUCKET="fraud-audit-archive"
EVENT_BUS_NAME="fraud-detection"
LOCALSTACK_IMAGE="localstack/localstack:3.4"
CONTAINER_NAME="localstack"
BACKEND_PORT=8000
FRONTEND_PORT=8501
PROJECT_ROOT="$(cd "$(dirname "$0")/.." && pwd)"

export AWS_ACCESS_KEY_ID=test
export AWS_SECRET_ACCESS_KEY=test
export AWS_DEFAULT_REGION=$REGION

# --- Helper functions ---
print_header() {
  echo ""
  echo "============================================================"
  echo "  $1"
  echo "============================================================"
}

print_step() {
  echo ""
  echo "--- [$1/$TOTAL_STEPS] $2 ---"
}

check_command() {
  command -v "$1" &>/dev/null
}

TOTAL_STEPS=6

print_header "Payment Fraud Detection (Python) — Local Setup"
echo "Project root: $PROJECT_ROOT"

###############################################################################
# STEP 1: Check prerequisites
###############################################################################
print_step 1 "Checking prerequisites"

# Python 3
if check_command python3; then
  echo "✓ Python: $(python3 --version)"
else
  echo "✗ Python 3 not found. Please install Python 3.9+ and try again."
  exit 1
fi

# pip3
if check_command pip3; then
  echo "✓ pip3 found"
else
  echo "✗ pip3 not found. Install with: sudo apt install python3-pip"
  exit 1
fi

# Docker
if check_command docker; then
  echo "✓ Docker: $(docker --version)"
else
  echo "✗ Docker not found. Please install Docker."
  exit 1
fi

# AWS CLI
if check_command aws; then
  echo "✓ AWS CLI: $(aws --version 2>&1 | head -1)"
else
  echo "✗ AWS CLI not found. Please install AWS CLI v2."
  exit 1
fi

# Install Python dependencies
echo ""
echo "⟳ Installing Python dependencies..."
pip3 install --quiet --break-system-packages \
  fastapi uvicorn boto3 pydantic streamlit requests 2>/dev/null \
  || pip3 install --quiet \
  fastapi uvicorn boto3 pydantic streamlit requests
echo "✓ Python dependencies installed"

###############################################################################
# STEP 2: Start LocalStack
###############################################################################
print_step 2 "Starting LocalStack"

# Ensure Docker is running
if ! sudo docker info &>/dev/null 2>&1; then
  echo "⟳ Starting Docker daemon..."
  sudo systemctl start docker
  sleep 2
fi

# Stop existing container if running
if sudo docker ps -q --filter "name=$CONTAINER_NAME" | grep -q . 2>/dev/null; then
  echo "⟳ Stopping existing LocalStack container..."
  sudo docker stop "$CONTAINER_NAME" >/dev/null 2>&1 || true
  sleep 2
fi
sudo docker rm "$CONTAINER_NAME" >/dev/null 2>&1 || true

# Start LocalStack
echo "⟳ Starting LocalStack container..."
sudo docker run -d --rm \
  -p 4566:4566 \
  -e SERVICES=dynamodb,events,iam,s3,sqs,sts \
  -v /var/run/docker.sock:/var/run/docker.sock \
  --name "$CONTAINER_NAME" \
  "$LOCALSTACK_IMAGE" >/dev/null

# Wait for ready
echo "⟳ Waiting for LocalStack..."
for i in $(seq 1 30); do
  if aws --endpoint-url=$ENDPOINT sts get-caller-identity >/dev/null 2>&1; then
    echo "✓ LocalStack ready (took ~$((i * 2))s)"
    break
  fi
  if [ "$i" -eq 30 ]; then
    echo "✗ LocalStack did not start in time"
    exit 1
  fi
  sleep 2
done

###############################################################################
# STEP 3: Deploy AWS resources
###############################################################################
print_step 3 "Deploying AWS resources"

# DynamoDB table
aws --endpoint-url=$ENDPOINT dynamodb create-table \
  --table-name "$TABLE_NAME" \
  --key-schema \
    AttributeName=pk,KeyType=HASH \
    AttributeName=sk,KeyType=RANGE \
  --attribute-definitions \
    AttributeName=pk,AttributeType=S \
    AttributeName=sk,AttributeType=S \
    AttributeName=gsiPk,AttributeType=S \
    AttributeName=gsiSk,AttributeType=S \
  --global-secondary-indexes '[{
    "IndexName": "DecisionByDate",
    "KeySchema": [
      {"AttributeName": "gsiPk", "KeyType": "HASH"},
      {"AttributeName": "gsiSk", "KeyType": "RANGE"}
    ],
    "Projection": {"ProjectionType": "ALL"}
  }]' \
  --billing-mode PAY_PER_REQUEST \
  --no-cli-pager >/dev/null 2>&1 || echo "  (table already exists)"
echo "✓ DynamoDB table: $TABLE_NAME"

# S3 bucket
aws --endpoint-url=$ENDPOINT s3 mb "s3://$AUDIT_BUCKET" \
  --no-cli-pager >/dev/null 2>&1 || echo "  (bucket already exists)"
echo "✓ S3 bucket: $AUDIT_BUCKET"

# EventBridge bus
aws --endpoint-url=$ENDPOINT events create-event-bus \
  --name "$EVENT_BUS_NAME" \
  --no-cli-pager >/dev/null 2>&1 || echo "  (bus already exists)"
echo "✓ EventBridge bus: $EVENT_BUS_NAME"

###############################################################################
# STEP 4: Seed test data
###############################################################################
print_step 4 "Seeding test data"

# Use the existing seed script from the parent project if available
SEED_SCRIPT="$(cd "$(dirname "$0")/../.." && pwd)/localstack/seed-data.sh"
if [ -f "$SEED_SCRIPT" ]; then
  bash "$SEED_SCRIPT"
else
  # Inline minimal seed for standalone usage
  echo "⟳ Seeding minimal test data..."

  # Helper: put customer profile
  put_profile() {
    aws --endpoint-url=$ENDPOINT dynamodb put-item \
      --table-name "$TABLE_NAME" \
      --item "{
        \"pk\": {\"S\": \"CUST#$1#$2\"},
        \"sk\": {\"S\": \"PROFILE\"},
        \"meanAmount\": {\"N\": \"$3\"},
        \"stdDevAmount\": {\"N\": \"$4\"},
        \"transactionCount90d\": {\"N\": \"$5\"},
        \"devices\": {\"L\": [{\"S\": \"device-001\"}, {\"S\": \"device-002\"}]},
        \"locations\": {\"L\": [{\"S\": \"51.5074,-0.1278\"}]},
        \"avgSessionDuration\": {\"N\": \"$6\"},
        \"lastUpdated\": {\"S\": \"2026-06-01T10:00:00Z\"}
      }" --no-cli-pager 2>/dev/null
  }

  # Helper: put beneficiary
  put_beneficiary() {
    aws --endpoint-url=$ENDPOINT dynamodb put-item \
      --table-name "$TABLE_NAME" \
      --item "{
        \"pk\": {\"S\": \"BENE#$1#$2\"},
        \"sk\": {\"S\": \"STATUS\"},
        \"flag\": {\"S\": \"$3\"},
        \"lastUpdated\": {\"S\": \"2026-05-15T08:00:00Z\"},
        \"reason\": {\"S\": \"$4\"}
      }" --no-cli-pager 2>/dev/null
  }

  # Low-risk debtor
  put_profile "101010" "10000001" "350" "80" "120" "150000"
  # Medium-risk debtor
  put_profile "202020" "20000001" "800" "250" "35" "90000"
  # High-value debtor
  put_profile "303030" "30000001" "8000" "3000" "80" "200000"
  # New customer
  put_profile "404040" "40000001" "150" "50" "3" "45000"

  # Clean creditor
  put_beneficiary "505050" "50000001" "NONE" "No adverse information"
  # High-risk creditor
  put_beneficiary "606060" "60000001" "HIGH_RISK" "Multiple fraud reports"
  # Mule-linked creditor
  put_beneficiary "707070" "70000001" "MULE_LINKED" "Linked to money mule network"

  echo "✓ Test data seeded (4 profiles + 3 beneficiary records)"
fi

###############################################################################
# STEP 5: Start FastAPI backend
###############################################################################
print_step 5 "Starting FastAPI backend (port $BACKEND_PORT)"

# Kill any existing process on the port
kill $(lsof -t -i :$BACKEND_PORT 2>/dev/null) 2>/dev/null || true

cd "$PROJECT_ROOT/backend"
AWS_ACCESS_KEY_ID=test \
AWS_SECRET_ACCESS_KEY=test \
AWS_DEFAULT_REGION=$REGION \
AWS_ENDPOINT_URL=$ENDPOINT \
FRAUD_DETECTION_TABLE=$TABLE_NAME \
AUDIT_BUCKET_NAME=$AUDIT_BUCKET \
EVENT_BUS_NAME=$EVENT_BUS_NAME \
  nohup python3 -m uvicorn main:app --host 0.0.0.0 --port $BACKEND_PORT \
  > /tmp/fraud-backend.log 2>&1 &

BACKEND_PID=$!
echo "✓ FastAPI backend started (PID: $BACKEND_PID, log: /tmp/fraud-backend.log)"

# Wait for backend to be ready
for i in $(seq 1 15); do
  if curl -s http://localhost:$BACKEND_PORT/health >/dev/null 2>&1; then
    echo "✓ Backend is responding"
    break
  fi
  if [ "$i" -eq 15 ]; then
    echo "⚠ Backend not responding yet (may still be starting)"
  fi
  sleep 1
done

###############################################################################
# STEP 6: Start Streamlit frontend
###############################################################################
print_step 6 "Starting Streamlit frontend (port $FRONTEND_PORT)"

# Kill any existing process on the port
kill $(lsof -t -i :$FRONTEND_PORT 2>/dev/null) 2>/dev/null || true

cd "$PROJECT_ROOT/frontend"
nohup streamlit run app.py \
  --server.headless true \
  --server.port $FRONTEND_PORT \
  --server.address 0.0.0.0 \
  > /tmp/fraud-frontend.log 2>&1 &

FRONTEND_PID=$!
echo "✓ Streamlit frontend started (PID: $FRONTEND_PID, log: /tmp/fraud-frontend.log)"

# Wait for frontend to be ready
for i in $(seq 1 15); do
  if curl -s -o /dev/null http://localhost:$FRONTEND_PORT/ 2>&1; then
    echo "✓ Frontend is responding"
    break
  fi
  if [ "$i" -eq 15 ]; then
    echo "⚠ Frontend not responding yet (may still be starting)"
  fi
  sleep 1
done

###############################################################################
# Done
###############################################################################

print_header "Local Environment Ready!"
echo ""
echo "  Frontend (Streamlit):  http://localhost:$FRONTEND_PORT"
echo "  Backend (FastAPI):     http://localhost:$BACKEND_PORT"
echo "  API Docs (Swagger):    http://localhost:$BACKEND_PORT/docs"
echo "  LocalStack:            $ENDPOINT"
echo ""
echo "  Backend log:   tail -f /tmp/fraud-backend.log"
echo "  Frontend log:  tail -f /tmp/fraud-frontend.log"
echo ""
echo "  To stop: ./payment-fraud-detection/localstack/stop-local.sh"
echo ""
echo "  NOTE: Set the API Base URL in the Streamlit sidebar to:"
echo "        http://localhost:$BACKEND_PORT"
echo ""
echo "============================================================"
