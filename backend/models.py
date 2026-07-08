"""
Domain models for the Payment Fraud Detection system.
"""

from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class ChannelType(str, Enum):
    MOBILE = "MOBILE"
    ONLINE_BANKING = "ONLINE_BANKING"
    API = "API"
    BRANCH = "BRANCH"
    PHONE = "PHONE"


class CopResult(str, Enum):
    MATCH = "MATCH"
    CLOSE_MATCH = "CLOSE_MATCH"
    NO_MATCH = "NO_MATCH"
    NOT_AVAILABLE = "NOT_AVAILABLE"


class Decision(str, Enum):
    ALLOW = "ALLOW"
    REVIEW = "REVIEW"
    BLOCK = "BLOCK"


class BeneficiaryFlag(str, Enum):
    NONE = "NONE"
    HIGH_RISK = "HIGH_RISK"
    MULE_LINKED = "MULE_LINKED"


# ---------------------------------------------------------------------------
# Request Models
# ---------------------------------------------------------------------------


class GeoLocation(BaseModel):
    latitude: float
    longitude: float


class BankAccount(BaseModel):
    sortCode: str
    accountNumber: str
    accountName: Optional[str] = None


class Channel(BaseModel):
    type: ChannelType
    deviceId: Optional[str] = None
    geoLocation: Optional[GeoLocation] = None
    sessionDuration: Optional[str] = None  # ISO-8601 duration string e.g. "PT120S"


class ConfirmationOfPayee(BaseModel):
    result: Optional[CopResult] = None
    matchedName: Optional[str] = None


class FasterPaymentRequest(BaseModel):
    messageId: str
    debtorAccount: BankAccount
    creditorAccount: BankAccount
    amount: float = Field(gt=0)
    currency: str = "GBP"
    paymentReference: Optional[str] = None
    confirmationOfPayee: Optional[ConfirmationOfPayee] = None
    channel: Optional[Channel] = None
    timestamp: Optional[str] = None


# ---------------------------------------------------------------------------
# Response Models
# ---------------------------------------------------------------------------


class RiskFactor(BaseModel):
    category: str
    explanation: str


class RiskBreakdown(BaseModel):
    amountScore: int
    copScore: int
    behaviouralScore: int
    channelScore: int


class FraudDecisionResponse(BaseModel):
    messageId: str
    decision: Decision
    riskScore: int
    breakdown: RiskBreakdown
    riskFactors: list[RiskFactor]
    timestamp: str


# ---------------------------------------------------------------------------
# Internal Models
# ---------------------------------------------------------------------------


class CustomerProfile(BaseModel):
    """Debtor's historical behavioural profile."""
    sortCode: str
    accountNumber: str
    meanAmount: float = 0.0
    stdDevAmount: float = 0.0
    transactionCount90d: int = 0
    knownDevices: list[str] = Field(default_factory=list)
    knownLocations: list[GeoLocation] = Field(default_factory=list)
    avgSessionDurationMs: float = 0.0
    lastUpdated: Optional[str] = None


class BeneficiaryStatus(BaseModel):
    """Creditor's risk flag from the beneficiary registry."""
    flag: BeneficiaryFlag = BeneficiaryFlag.NONE
    lastUpdated: Optional[str] = None


class ScorerResult(BaseModel):
    """Output from a single component scorer."""
    score: int
    explanation: str


class RiskAssessment(BaseModel):
    """Composite result from the risk scoring engine."""
    riskScore: int
    amountScore: int
    copScore: int
    behaviouralScore: int
    channelScore: int
    riskFactors: list[RiskFactor]


class FraudDecision(BaseModel):
    """Output from the decision engine."""
    decision: Decision
    riskScore: int
    topRiskFactors: list[RiskFactor]
    thresholdOverride: bool


class ConfirmPaymentRequest(BaseModel):
    messageId: str


class ConfirmPaymentResponse(BaseModel):
    messageId: str
    status: str
    message: str
