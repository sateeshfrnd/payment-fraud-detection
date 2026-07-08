# Payment Fraud Detection — FastAPI Backend

A Python/FastAPI replica for fraud detection service. Provides scoring logic, validation rules, and decision thresholds.

## Quick Start

```bash
# Install dependencies
.venv\Scripts\activate                                                          
uv sync

# Ensure LocalStack is running with seeded data (or use start-local.sh first)

# Start the FastAPI server
cd payment-fraud-detection/backend
uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```

The API is available at **http://localhost:8000**.

## Endpoints

| Method | Path | Description |
|--------|------|-------------|
| POST | `/fraud-check` | Evaluate a payment for fraud risk |
| POST | `/confirm-payment` | Confirm a REVIEW'd payment |
| GET | `/health` | Health check |
| GET | `/docs` | Interactive Swagger UI (auto-generated) |

## Architecture

```
main.py          → FastAPI app, endpoint handlers, orchestration
models.py        → Pydantic models (request, response, domain)
validation.py    → Request field validation (mirrors Java RequestValidator)
scoring.py       → 4 component scorers + RiskScoringEngine
decision.py      → DecisionEngine (score→decision mapping + overrides)
repository.py    → DynamoDB reads/writes, EventBridge publishing, S3 archival
```

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `FRAUD_DETECTION_TABLE` | `FraudDetection` | DynamoDB table name |
| `AUDIT_BUCKET_NAME` | `fraud-audit-archive` | S3 bucket for audit archive |
| `EVENT_BUS_NAME` | `fraud-detection` | EventBridge bus name |
| `AWS_ENDPOINT_URL` | `http://localhost:4566` | LocalStack endpoint |
| `AWS_DEFAULT_REGION` | `us-east-1` | AWS region |
| `AWS_ACCESS_KEY_ID` | `test` | AWS credentials |
| `AWS_SECRET_ACCESS_KEY` | `test` | AWS credentials |

## Using with the Streamlit Frontend

Update the API Base URL in the Streamlit sidebar to `http://localhost:8000` to point at this FastAPI backend.

