"""
Payment Fraud Detection — Streamlit Frontend

Payment Fraud Check connects to the  backend API.

Usage:
    streamlit run payment-fraud-detection/frontend/app.py
"""

import uuid
import re
from datetime import datetime, timezone

import requests
import streamlit as st

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

API_BASE_URL = st.sidebar.text_input(
    "API Base URL",
    value="http://localhost:8080",
    help="Base URL of the fraud detection API (dev server proxy or direct LocalStack URL)",
)

FRAUD_CHECK_ENDPOINT = f"{API_BASE_URL.rstrip('/')}/fraud-check"
CONFIRM_PAYMENT_ENDPOINT = f"{API_BASE_URL.rstrip('/')}/confirm-payment"

# ---------------------------------------------------------------------------
# API Client
# ---------------------------------------------------------------------------

def submit_fraud_check(payload: dict) -> dict:
    """POST the payment request to the fraud-check endpoint."""
    try:
        resp = requests.post(FRAUD_CHECK_ENDPOINT, json=payload, timeout=10)
        if resp.status_code == 200:
            return {"success": True, "data": resp.json()}
        else:
            return {"success": False, "error": f"HTTP {resp.status_code}: {resp.text[:300]}"}
    except requests.Timeout:
        return {"success": False, "error": "Request timed out. Please try again."}
    except requests.ConnectionError:
        return {"success": False, "error": "Unable to connect. Please check your connection and try again."}
    except Exception as e:
        return {"success": False, "error": str(e)}


def confirm_payment(message_id: str) -> dict:
    """POST to confirm-payment endpoint for REVIEW decisions."""
    try:
        resp = requests.post(CONFIRM_PAYMENT_ENDPOINT, json={"messageId": message_id}, timeout=10)
        if resp.status_code == 200:
            return {"success": True, "data": resp.json()}
        else:
            return {"success": False, "error": f"HTTP {resp.status_code}: {resp.text[:300]}"}
    except Exception as e:
        return {"success": False, "error": str(e)}
    
# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------
def validate_sort_code(value: str, label: str) -> list[str]:
    """Validate a sort code field. Accepts NN-NN-NN or NNNNNN (6 digits after stripping hyphens)."""
    errors = []
    if not value or value.strip() == "":
        errors.append(f"{label} is required")
        return errors
    stripped = value.replace("-", "")
    if not re.match(r"^\d{6}$", stripped):
        errors.append(f"{label} must be 6 digits")
    return errors


def validate_account_number(value: str, label: str) -> list[str]:
    """Validate an account number field. Must be exactly 8 digits."""
    errors = []
    if not value or value.strip() == "":
        errors.append(f"{label} is required")
        return errors
    if not re.match(r"^\d{8}$", value):
        errors.append(f"{label} must be 8 digits")
    return errors


def validate_amount(value: str) -> list[str]:
    """Validate the amount field."""
    errors = []
    if not value or value.strip() == "":
        errors.append("Amount is required")
        return errors
    try:
        num = float(value)
    except ValueError:
        errors.append("Amount must be a number between 0.01 and 999,999,999.99")
        return errors
    if "." in value:
        decimal_part = value.split(".")[1]
        if len(decimal_part) > 2:
            errors.append("Amount must have at most 2 decimal places")
            return errors
    if num < 0.01 or num > 999_999_999.99:
        errors.append("Amount must be a number between 0.01 and 999,999,999.99")
    return errors


def validate_channel_type(value: str) -> list[str]:
    """Validate the channel type field."""
    errors = []
    if not value or value.strip() == "":
        errors.append("Channel type is required")
    return errors


def validate_form(data: dict) -> list[str]:
    """Run all validations and return a flat list of error messages."""
    errors = []
    errors.extend(validate_sort_code(data["debtor_sort_code"], "Debtor sort code"))
    errors.extend(validate_account_number(data["debtor_account_number"], "Debtor account number"))
    errors.extend(validate_sort_code(data["creditor_sort_code"], "Creditor sort code"))
    errors.extend(validate_account_number(data["creditor_account_number"], "Creditor account number"))
    errors.extend(validate_amount(data["amount"]))
    errors.extend(validate_channel_type(data["channel_type"]))
    return errors


# ---------------------------------------------------------------------------
# UI: Build Payload
# ---------------------------------------------------------------------------
def build_payment_request(data: dict) -> dict:
    """Build the FasterPaymentRequest JSON payload from form data."""
    return {
        "messageId": str(uuid.uuid4()),
        "debtorAccount": {
            "sortCode": data["debtor_sort_code"].replace("-", ""),
            "accountNumber": data["debtor_account_number"],
            "accountName": data["debtor_account_name"],
        },
        "creditorAccount": {
            "sortCode": data["creditor_sort_code"].replace("-", ""),
            "accountNumber": data["creditor_account_number"],
            "accountName": data["creditor_account_name"],
        },
        "amount": float(data["amount"]),
        "currency": "GBP",
        "paymentReference": data["payment_reference"] or None,
        "confirmationOfPayee": {
            "result": data["cop_result"] if data["cop_result"] else None,
            "matchedName": data["cop_matched_name"] or None,
        },
        "channel": {
            "type": data["channel_type"],
            "deviceId": None,
            "geoLocation": None,
            "sessionDuration": None,
        },
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }

# ---------------------------------------------------------------------------
# UI: Result Display
# ---------------------------------------------------------------------------


def display_result(response: dict):
    """Render the fraud decision response."""
    decision = response.get("decision", "UNKNOWN")
    risk_score = response.get("riskScore", 0)
    breakdown = response.get("breakdown", {})
    risk_factors = response.get("riskFactors", [])
    message_id = response.get("messageId", "")

    # Decision header
    if decision == "ALLOW":
        st.success("Payment Approved")
    elif decision == "REVIEW":
        st.warning("Payment Held for Review")
    elif decision == "BLOCK":
        st.error("Payment Blocked")
    else:
        st.error(f"Unknown decision: {decision}")

    # Risk score
    st.metric("Risk Score", f"{risk_score} / 100")

    # Breakdown
    st.subheader("Score Breakdown")
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Amount", breakdown.get("amountScore", 0))
    col2.metric("CoP", breakdown.get("copScore", 0))
    col3.metric("Behavioural", breakdown.get("behaviouralScore", 0))
    col4.metric("Channel", breakdown.get("channelScore", 0))

    # Risk factors
    if risk_factors:
        st.subheader("Risk Factors")
        for factor in risk_factors:
            category = factor.get("category", "unknown")
            explanation = factor.get("explanation", "")
            st.markdown(f"- **{category}**: {explanation}")

    # Confirm button for REVIEW decisions
    if decision == "REVIEW":
        st.divider()
        if st.button("Confirm Payment", type="primary", key="confirm_btn"):
            result = confirm_payment(message_id)
            if result["success"]:
                st.success("✅ Payment confirmed and submitted for processing")
            else:
                st.error(f"Confirmation failed: {result['error']}")

    # Block message
    if decision == "BLOCK":
        st.caption("This payment cannot proceed due to fraud risk.")

# ---------------------------------------------------------------------------
# Main App
# ---------------------------------------------------------------------------
st.set_page_config(page_title="Payment Fraud Check", page_icon="🔒", layout="centered")

st.title("🔒 Payment Fraud Check")
st.caption("Submit a Faster Payment for real-time fraud scoring")

# Initialize session state
if "result" not in st.session_state:
    st.session_state.result = None

# ---------------------------------------------------------------------------
# Payment Form
# ---------------------------------------------------------------------------
with st.form("payment_form"):
    # Debtor Account
    st.subheader("Debtor Account")
    col1, col2 = st.columns(2)
    debtor_sort_code = col1.text_input("Sort Code", placeholder="NN-NN-NN", max_chars=8, key="debtor_sc")
    debtor_account_number = col2.text_input("Account Number", placeholder="12345678", max_chars=8, key="debtor_an")
    debtor_account_name = st.text_input("Account Name (optional)", max_chars=70, key="debtor_name")

    # Creditor Account
    st.subheader("Creditor Account")
    col1, col2 = st.columns(2)
    creditor_sort_code = col1.text_input("Sort Code", placeholder="NN-NN-NN", max_chars=8, key="creditor_sc")
    creditor_account_number = col2.text_input("Account Number", placeholder="12345678", max_chars=8, key="creditor_an")
    creditor_account_name = st.text_input("Account Name (optional)", max_chars=70, key="creditor_name")

    # Payment Details
    st.subheader("Payment Details")
    col1, col2 = st.columns(2)
    amount = col1.text_input("Amount (GBP)", placeholder="0.00", key="amount_input")
    payment_reference = col2.text_input("Payment Reference (optional)", max_chars=18, key="pay_ref")

    channel_type = st.selectbox(
        "Channel Type",
        options=["", "MOBILE", "ONLINE_BANKING", "API", "BRANCH", "PHONE"],
        format_func=lambda x: "-- Select Channel --" if x == "" else x,
        key="channel_select",
    )

    # Confirmation of Payee
    st.subheader("Confirmation of Payee")
    col1, col2 = st.columns(2)
    cop_result = col1.selectbox(
        "CoP Result",
        options=["", "MATCH", "CLOSE_MATCH", "NO_MATCH", "NOT_AVAILABLE"],
        format_func=lambda x: "-- Select CoP Result --" if x == "" else x,
        key="cop_select",
    )
    cop_matched_name = col2.text_input("CoP Matched Name (optional)", max_chars=70, key="cop_name")

    # Submit
    submitted = st.form_submit_button("Check Payment", use_container_width=True, type="primary")

# ---------------------------------------------------------------------------
# Form Submission
# ---------------------------------------------------------------------------

if submitted:
    form_data = {
        "debtor_sort_code": debtor_sort_code,
        "debtor_account_number": debtor_account_number,
        "debtor_account_name": debtor_account_name,
        "creditor_sort_code": creditor_sort_code,
        "creditor_account_number": creditor_account_number,
        "creditor_account_name": creditor_account_name,
        "amount": amount,
        "payment_reference": payment_reference,
        "channel_type": channel_type,
        "cop_result": cop_result,
        "cop_matched_name": cop_matched_name,
    }

    # Validate
    errors = validate_form(form_data)
    if errors:
        for err in errors:
            st.error(err)
    else:
        # Build and submit
        payload = build_payment_request(form_data)
        st.write(payload)
        with st.spinner("Checking payment..."):
            result = submit_fraud_check(payload)

        if result["success"]:
            st.session_state.result = result["data"]
        else:
            st.error(result["error"])

# ---------------------------------------------------------------------------
# Display Result
# ---------------------------------------------------------------------------

if st.session_state.result:
    st.divider()
    display_result(st.session_state.result)

    # New Payment button
    if st.button("New Payment"):
        st.session_state.result = None
        st.rerun()

# ---------------------------------------------------------------------------
# Sidebar Info
# ---------------------------------------------------------------------------

st.sidebar.divider()
st.sidebar.subheader("Test Accounts")
st.sidebar.markdown("""
**Low-risk debtor:** `101010` / `10000001`  
**Medium-risk debtor:** `202020` / `20000001`  
**High-value debtor:** `303030` / `30000001`  
**New customer:** `404040` / `40000001`  

**Clean creditor:** `505050` / `50000001`  
**High-risk creditor:** `606060` / `60000001`  
**Mule-linked creditor:** `707070` / `70000001`  
""")

st.sidebar.divider()
st.sidebar.caption("Payment Fraud Detection v1.0.0")