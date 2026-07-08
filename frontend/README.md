# Payment Fraud Detection — Streamlit Frontend

A Streamlit replica of the vanilla JS Payment Fraud Check UI.

## Quick Start

```bash
# Install dependencies
pip install -r payment-fraud-detection/frontend/requirements.txt

# Start the Streamlit app (ensure the backend is running first)
streamlit run payment-fraud-detection/frontend/app.py
```

The app opens at **http://localhost:8501** by default.

## Prerequisites

- Python 3.9+
- The backend must be running (either via `./localstack/start-local.sh` or separately)

## Configuration

Use the sidebar to configure the API base URL. Defaults to `http://localhost:8080` (the dev server proxy).

## Features

- Streamlit frontend UI (debtor/creditor accounts, amount, channel, CoP)
- Client-side validation matching the original rules
- Real-time API submission with loading spinner
- Color-coded decision display (green/amber/red for ALLOW/REVIEW/BLOCK)
- Score breakdown with per-scorer metrics
- Risk factor explanations
- Confirm Payment flow for REVIEW decisions
- Sidebar with test account reference
