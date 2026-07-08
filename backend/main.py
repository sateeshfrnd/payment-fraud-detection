"""
Payment Fraud Detection — FastAPI Backend

A Python/FastAPI for the fraud detection service.
Provides the /fraud-check and /confirm-payment endpoints with identical
scoring logic, validation rules, and decision thresholds.

Usage:
    uvicorn main:app --host 0.0.0.0 --port 8000 --reload

"""
import logging
import threading
from datetime import datetime, timezone

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from models import (
    BeneficiaryFlag,
    BeneficiaryStatus,
    ConfirmPaymentRequest,
    ConfirmPaymentResponse,
    CustomerProfile,
    Decision,
    FasterPaymentRequest,
    FraudDecisionResponse,
    RiskBreakdown,
    RiskFactor,
)

from validation import validate_request
from scoring import compute_risk_assessment
from decision import decide
from repository import (
    get_beneficiary_status,
    get_customer_profile,
    publish_decision_event,
    write_audit_record,
)

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("fraud-detection")

# ---------------------------------------------------------------------------
# FastAPI App
# ---------------------------------------------------------------------------

app = FastAPI(
    title="Payment Fraud Detection API",
    description="Real-time fraud scoring for UK Faster Payments",
    version="1.0.0",
)

# CORS — allow all origins for local development
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@app.post("/fraud-check", response_model=FraudDecisionResponse)
def fraud_check(request: FasterPaymentRequest) -> FraudDecisionResponse:
    """
    Evaluate a Faster Payment request for fraud risk.

    Flow:
    1. Validate request fields
    2. Load customer profile from DynamoDB
    3. Load beneficiary status from DynamoDB
    4. Compute risk score (4 component scorers)
    5. Apply decision logic (overrides, thresholds)
    6. Publish decision event (fire-and-forget)
    7. Write audit record (fire-and-forget)
    8. Return decision response
    """
    # 1. Validate
    errors = validate_request(request)
    if errors:
        raise HTTPException(
            status_code=400,
            detail={"errors": [{"field": e.field, "message": e.message} for e in errors]},
        )

    # 2. Load customer profile
    profile = get_customer_profile(
        request.debtorAccount.sortCode,
        request.debtorAccount.accountNumber,
    )
    if profile is None:
        # Default profile for unknown customers
        profile = CustomerProfile(
            sortCode=request.debtorAccount.sortCode,
            accountNumber=request.debtorAccount.accountNumber,
        )

    # 3. Load beneficiary status
    beneficiary_status = get_beneficiary_status(
        request.creditorAccount.sortCode,
        request.creditorAccount.accountNumber,
    )

    # 4. Compute risk assessment
    assessment = compute_risk_assessment(request, profile, beneficiary_status)

    # 5. Apply decision logic
    fraud_decision = decide(assessment, beneficiary_status, profile, request)

    # 6. Build response
    timestamp = datetime.now(timezone.utc).isoformat()
    response = FraudDecisionResponse(
        messageId=request.messageId,
        decision=fraud_decision.decision,
        riskScore=fraud_decision.riskScore,
        breakdown=RiskBreakdown(
            amountScore=assessment.amountScore,
            copScore=assessment.copScore,
            behaviouralScore=assessment.behaviouralScore,
            channelScore=assessment.channelScore,
        ),
        riskFactors=fraud_decision.topRiskFactors,
        timestamp=timestamp,
    )

    # 7. Fire-and-forget: publish event + write audit (in background thread)
    request_data = request.model_dump()
    threading.Thread(
        target=_async_post_decision,
        args=(request_data, response),
        daemon=True,
    ).start()

    return response


@app.post("/confirm-payment", response_model=ConfirmPaymentResponse)
def confirm_payment(request: ConfirmPaymentRequest) -> ConfirmPaymentResponse:
    """
    Confirm a payment that received a REVIEW decision.
    Returns a success response (stub — same as the Java/LocalStack implementation).
    """
    return ConfirmPaymentResponse(
        messageId=request.messageId,
        status="CONFIRMED",
        message="Payment confirmed and submitted for processing",
    )


@app.get("/health")
def health_check():
    """Health check endpoint."""
    return {"status": "healthy", "service": "payment-fraud-detection"}


# ---------------------------------------------------------------------------
# Background Tasks
# ---------------------------------------------------------------------------


def _async_post_decision(request_data: dict, response: FraudDecisionResponse) -> None:
    """Publish event and write audit record in background."""
    try:
        publish_decision_event(request_data, response)
    except Exception as e:
        logger.error("Background event publish failed: %s", e)

    try:
        write_audit_record(request_data, response)
    except Exception as e:
        logger.error("Background audit write failed: %s", e)
