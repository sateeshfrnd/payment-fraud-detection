# Payment Fraud Detection (Python)

A real-time fraud detection system for UK Faster Payments, built with **FastAPI** for the backend and **Streamlit** for the frontend, connected to **LocalStack** (DynamoDB, S3, EventBridge) running in Docker.

## What This Application Does

When a bank customer initiates a Faster Payment (UK instant bank transfer), this system evaluates the payment in real-time and returns one of three decisions:

- **ALLOW** — Payment is safe, proceed
- **REVIEW** — Payment is suspicious, hold for manual review
- **BLOCK** — Payment is high-risk, reject it

The decision is based on four risk scorers that each contribute 0–25 points for a composite score of 0–100.

## Architecture

```
┌────────────────────────┐         ┌────────────────────────┐
│   Streamlit Frontend   │  HTTP   │    FastAPI Backend      │
│   (port 8501)          │ ──────► │    (port 8000)          │
│                        │         │                         │
│  • Payment form        │         │  • Validate request     │
│  • Validation          │         │  • Load customer profile│
│  • Result display      │         │  • Load beneficiary flag│
│  • Confirm flow        │         │  • Score risk (4 scorers)│
└────────────────────────┘         │  • Decide ALLOW/REVIEW/ │
                                   │    BLOCK                 │
                                   │  • Write audit record    │
                                   │  • Publish event         │
                                   └───────────┬─────────────┘
                                               │
                                               │ boto3 (HTTP :4566)
                                               ▼
                                   ┌────────────────────────┐
                                   │   LocalStack (Docker)   │
                                   │                         │
                                   │  • DynamoDB (profiles,  │
                                   │    beneficiaries, audit)│
                                   │  • S3 (audit archive)   │
                                   │  • EventBridge (events) │
                                   └────────────────────────┘
```

## Project Structure

```
payment-fraud-detection/
│
├── backend/                     # FastAPI backend (Python)
│   ├── main.py                  # FastAPI app, endpoints, orchestration
│   ├── models.py                # Pydantic models (request, response, domain)
│   ├── validation.py            # Request field validation
│   ├── scoring.py               # 4 component scorers + risk scoring engine
│   ├── decision.py              # Decision engine (score → decision + overrides)
│   ├── repository.py            # DynamoDB reads/writes, EventBridge, S3
│   ├── requirements.txt         # Python dependencies
│   └── README.md                # Backend-specific documentation
│
├── frontend/                    # Streamlit frontend (Python)
│   ├── app.py                   # Streamlit application
│   ├── requirements.txt         # Python dependencies
│   └── README.md                # Frontend-specific documentation
│
├── localstack/                  # Local development scripts
│   ├── start-local.sh           # One-command full setup
│   ├── stop-local.sh            # Tear down everything
│   └── seed-data.sh             # Seed test data independently
│
└── README.md                    # This file
```

## Quick Start

### Prerequisites

| Tool | Version | Purpose |
|------|---------|---------|
| Python | 3.9+ | Backend and frontend runtime |
| Docker | Any | Run LocalStack |
| AWS CLI | v2 | Create tables and seed data (setup scripts only) |
| pip | Any | Install Python packages |

### Running Locally (VS Code or any terminal)

```bash
# 1. Clone the repository
git clone <repo-url>

# 2. Navigate into the project
cd payment-fraud-detection

# 3. Make the script executable (first time only)
chmod +x localstack/start-local.sh

# 4. Run it
./localstack/start-local.sh
```

That's it. The script installs all Python dependencies, starts Docker, creates AWS resources, seeds test data, and launches both the backend and frontend.

### One-Command Setup (if already inside the parent repo)

```bash
./payment-fraud-detection/localstack/start-local.sh
```

This single script:
1. Checks all prerequisites
2. Installs Python packages (FastAPI, Streamlit, boto3, etc.)
3. Starts LocalStack in Docker (fake DynamoDB, S3, EventBridge)
4. Creates the DynamoDB table, S3 bucket, and EventBridge bus
5. Seeds test data (customer profiles + beneficiary records)
6. Starts the FastAPI backend on port **8000**
7. Starts the Streamlit frontend on port **8501**

### After Startup

| Service | URL | Description |
|---------|-----|-------------|
| Frontend | http://localhost:8501 | Streamlit payment form UI |
| Backend | http://localhost:8000 | FastAPI fraud detection API |
| Swagger Docs | http://localhost:8000/docs | Interactive API documentation |
| LocalStack | http://localhost:4566 | Fake AWS services |

**Important:** In the Streamlit sidebar, set the API Base URL to `http://localhost:8000`.

### Stop Everything

```bash
./payment-fraud-detection/localstack/stop-local.sh
```

## How the Risk Scoring Works

### Four Component Scorers

Each scorer evaluates one dimension of risk and contributes 0–25 points:

| Scorer | File | What it evaluates | Score examples |
|--------|------|-------------------|----------------|
| **Amount** | `scoring.py` | How unusual is this amount compared to the customer's history? | £150 for a customer averaging £350 → 0. £9500 for a customer averaging £800 → 25 |
| **CoP** | `scoring.py` | Does the recipient name match the account? (Confirmation of Payee) | MATCH → 0, CLOSE_MATCH → 10, NO_MATCH → 22, absent → 15 |
| **Behavioural** | `scoring.py` | Is the session unusually fast? | Session ≥ 50% of avg → 0. Session < 50% → 10-25 |
| **Channel** | `scoring.py` | Unknown device? Far from usual location? Phone channel? | Unknown device → +10, far location → +15, PHONE → +5 |

### Decision Thresholds

| Composite Score | Decision |
|-----------------|----------|
| 0–30 | ALLOW |
| 31–70 | REVIEW |
| 71–100 | BLOCK |

### Override Rules

| Condition | Effect |
|-----------|--------|
| Creditor flagged as **MULE_LINKED** | Always BLOCK regardless of score |
| Creditor flagged as **HIGH_RISK** | Minimum score forced to 71 (BLOCK) |
| Amount exceeds mean + 3σ (or £500 for new customers) | Minimum decision elevated to REVIEW |

## Backend Details

### Endpoints

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/fraud-check` | Evaluate a payment for fraud risk |
| `POST` | `/confirm-payment` | Confirm a payment held for REVIEW |
| `GET` | `/health` | Health check |
| `GET` | `/docs` | Swagger UI (auto-generated by FastAPI) |

### Request Body (`POST /fraud-check`)

```json
{
  "messageId": "uuid-string",
  "debtorAccount": {
    "sortCode": "101010",
    "accountNumber": "10000001",
    "accountName": "John Doe"
  },
  "creditorAccount": {
    "sortCode": "505050",
    "accountNumber": "50000001",
    "accountName": "Jane Smith"
  },
  "amount": 150.00,
  "currency": "GBP",
  "paymentReference": "Rent June",
  "confirmationOfPayee": {
    "result": "MATCH",
    "matchedName": "Jane Smith"
  },
  "channel": {
    "type": "MOBILE",
    "deviceId": "device-001",
    "geoLocation": { "latitude": 51.5074, "longitude": -0.1278 },
    "sessionDuration": "PT120S"
  },
  "timestamp": "2026-06-16T10:00:00Z"
}
```

### Response Body

```json
{
  "messageId": "uuid-string",
  "decision": "ALLOW",
  "riskScore": 10,
  "breakdown": {
    "amountScore": 0,
    "copScore": 0,
    "behaviouralScore": 0,
    "channelScore": 10
  },
  "riskFactors": [
    {
      "category": "channel",
      "explanation": "Channel risk (score=10): unknown device"
    }
  ],
  "timestamp": "2026-06-18T06:46:25.474057+00:00"
}
```

### Validation Rules

| Field | Rule |
|-------|------|
| `debtorAccount.sortCode` | Required, exactly 6 digits |
| `debtorAccount.accountNumber` | Required, exactly 8 digits |
| `creditorAccount.sortCode` | Required, exactly 6 digits |
| `creditorAccount.accountNumber` | Required, exactly 8 digits |
| `amount` | Required, between £0.01 and £1,000,000.00 |
| `currency` | Required, must be `GBP` |
| `channel.type` | Required, one of: MOBILE, ONLINE_BANKING, API, BRANCH, PHONE |
| `paymentReference` | Optional, max 18 characters |

### Backend Module Responsibilities

| Module | Responsibility |
|--------|---------------|
| `main.py` | FastAPI app setup, endpoint handlers, CORS, background tasks |
| `models.py` | All Pydantic data models (enums, requests, responses, internal types) |
| `validation.py` | Full-pass request validation (collects all errors, never short-circuits) |
| `scoring.py` | Four scorer functions + `compute_risk_assessment()` orchestrator |
| `decision.py` | `decide()` function — maps score to decision, applies overrides |
| `repository.py` | DynamoDB reads (profiles, beneficiaries), audit writes, S3 archive, EventBridge publish |

## Frontend Details

The Streamlit app (`frontend/app.py`) replicates the original HTML/JS form:

- **Payment form** with debtor/creditor accounts, amount, channel, CoP fields
- **Client-side validation** matching the same rules as the backend
- **API submission** with loading spinner
- **Color-coded results**: green (ALLOW), amber (REVIEW), red (BLOCK)
- **Score breakdown** showing each scorer's contribution
- **Risk factor explanations**
- **Confirm Payment** button for REVIEW decisions
- **Sidebar** with test account reference and API URL configuration

## Test Data

After seeding, the following accounts are available:

| Role | Sort Code | Account | Characteristics |
|------|-----------|---------|-----------------|
| Debtor (low-risk) | `101010` | `10000001` | Mean £350, 120 txns, stable customer |
| Debtor (medium-risk) | `202020` | `20000001` | Mean £800, 35 txns |
| Debtor (high-value) | `303030` | `30000001` | Mean £8000, 80 txns |
| Debtor (new customer) | `404040` | `40000001` | Mean £150, 3 txns only |
| Creditor (clean) | `505050` | `50000001` | Flag: NONE |
| Creditor (high-risk) | `606060` | `60000001` | Flag: HIGH_RISK |
| Creditor (mule-linked) | `707070` | `70000001` | Flag: MULE_LINKED |

### Example Scenarios

| Scenario | Expected |
|----------|----------|
| Low-risk debtor (`101010/10000001`) → clean creditor (`505050/50000001`), £150, MATCH | **ALLOW** |
| Medium debtor (`202020/20000001`) → clean creditor, £5000, MATCH | **REVIEW** |
| New customer (`404040/40000001`) → high-risk creditor (`606060/60000001`), £9500, NO_MATCH | **BLOCK** |
| Any debtor → mule creditor (`707070/70000001`), any amount | **BLOCK** |

## Environment Variables

| Variable | Default | Used by |
|----------|---------|---------|
| `FRAUD_DETECTION_TABLE` | `FraudDetection` | Backend (DynamoDB table name) |
| `AUDIT_BUCKET_NAME` | `fraud-audit-archive` | Backend (S3 bucket for audit) |
| `EVENT_BUS_NAME` | `fraud-detection` | Backend (EventBridge bus name) |
| `AWS_ENDPOINT_URL` | `http://localhost:4566` | Backend (LocalStack endpoint) |
| `AWS_DEFAULT_REGION` | `us-east-1` | Backend + scripts |
| `AWS_ACCESS_KEY_ID` | `test` | Fake credentials for LocalStack |
| `AWS_SECRET_ACCESS_KEY` | `test` | Fake credentials for LocalStack |

## Technology Stack

| Component | Technology | Purpose |
|-----------|-----------|---------|
| Backend | FastAPI + Uvicorn | HTTP API server |
| Frontend | Streamlit | Interactive web UI |
| Database | DynamoDB (via LocalStack) | Customer profiles, beneficiary flags, audit records |
| File Storage | S3 (via LocalStack) | Long-term audit archive |
| Events | EventBridge (via LocalStack) | Decision event publishing |
| AWS SDK | boto3 | Python ↔ AWS/LocalStack communication |
| Local Infra | LocalStack (Docker) | Fake AWS services — no account needed |
| Setup Scripts | Bash + AWS CLI | One-time table creation and data seeding |
| Data Validation | Pydantic | Request/response serialization and validation |

## Running Individual Components

### Backend only

```bash
cd payment-fraud-detection/backend
pip install -r requirements.txt

AWS_ENDPOINT_URL=http://localhost:4566 \
AWS_ACCESS_KEY_ID=test \
AWS_SECRET_ACCESS_KEY=test \
  uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```

### Frontend only

```bash
cd payment-fraud-detection/frontend
pip install -r requirements.txt
streamlit run app.py --server.port 8501
```

### Seed data only (requires LocalStack running)

```bash
./payment-fraud-detection/localstack/seed-data.sh
```

## Troubleshooting

| Issue | Fix |
|-------|-----|
| `ModuleNotFoundError: No module named 'fastapi'` | Run `pip install -r payment-fraud-detection/backend/requirements.txt` |
| `Connection refused` on port 8000 | Backend isn't running — check `/tmp/fraud-backend.log` |
| `Connection refused` on port 4566 | LocalStack isn't running — start it with Docker |
| Streamlit shows "Unable to connect" | Set the sidebar API URL to `http://localhost:8000` |
| DynamoDB returns empty results | Run the seed script: `./payment-fraud-detection/localstack/seed-data.sh` |
| Docker permission denied | `sudo usermod -aG docker $USER` then log out/in |
| Port already in use | Kill the process: `kill $(lsof -t -i :8000)` or change the port |

## Logs

| Log | Location |
|-----|----------|
| Backend (FastAPI) | `/tmp/fraud-backend.log` or terminal stdout |
| Frontend (Streamlit) | `/tmp/fraud-frontend.log` or terminal stdout |
| LocalStack | `docker logs localstack` |

## Verifying LocalStack Services and Data

You can inspect LocalStack from your terminal using the AWS CLI pointed at port 4566:

```bash
# Set credentials (or export once in your shell)
export AWS_ACCESS_KEY_ID=test
export AWS_SECRET_ACCESS_KEY=test
export AWS_DEFAULT_REGION=us-east-1
```

### DynamoDB

```bash
# List tables
aws --endpoint-url=http://localhost:4566 dynamodb list-tables

# Count all items in the table
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
```

### S3 (Audit Archive)

```bash
# List buckets
aws --endpoint-url=http://localhost:4566 s3 ls

# List archived audit files
aws --endpoint-url=http://localhost:4566 s3 ls s3://fraud-audit-archive/ --recursive
```

### EventBridge

```bash
# List event buses
aws --endpoint-url=http://localhost:4566 events list-event-buses
```

### Docker

```bash
# Check if LocalStack is running
docker ps

# View LocalStack container logs
docker logs localstack
```

> **Note:** You do not need to go inside the Docker container. All commands run from your local terminal and talk to LocalStack over HTTP on port 4566.
