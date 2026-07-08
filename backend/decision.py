"""
Maps a composite risk score to a fraud decision (ALLOW, REVIEW, or BLOCK),
applying beneficiary overrides and dynamic threshold overrides.

Decision mapping:
    [0, 30]  → ALLOW
    [31, 70] → REVIEW
    [71, 100] → BLOCK

Beneficiary overrides:
    HIGH_RISK   → minimum score 71 (maps to BLOCK)
    MULE_LINKED → always BLOCK regardless of score

Dynamic threshold override:
    If amount exceeds mean + 3σ (or £500 for low-history accounts),
    the minimum decision is REVIEW.
"""

from models import (
    BeneficiaryFlag,
    BeneficiaryStatus,
    CustomerProfile,
    Decision,
    FasterPaymentRequest,
    FraudDecision,
    RiskAssessment,
    RiskFactor,
)

ALLOW_UPPER_BOUND = 30
REVIEW_UPPER_BOUND = 70
HIGH_RISK_MINIMUM_SCORE = 71
MIN_TRANSACTIONS_FOR_HISTORY = 5
DEFAULT_THRESHOLD = 500.0
STDDEV_MULTIPLIER = 3
MAX_TOP_RISK_FACTORS = 3


def _map_score_to_decision(risk_score: int) -> Decision:
    """Map a numeric risk score to a Decision enum value."""
    if risk_score <= ALLOW_UPPER_BOUND:
        return Decision.ALLOW
    elif risk_score <= REVIEW_UPPER_BOUND:
        return Decision.REVIEW
    else:
        return Decision.BLOCK


def _exceeds_dynamic_threshold(request: FasterPaymentRequest, profile: CustomerProfile) -> bool:
    """Check if the payment amount exceeds the debtor's dynamic threshold."""
    amount = request.amount

    if profile.transactionCount90d < MIN_TRANSACTIONS_FOR_HISTORY:
        threshold = DEFAULT_THRESHOLD
    else:
        threshold = profile.meanAmount + (STDDEV_MULTIPLIER * profile.stdDevAmount)

    return amount > threshold


def _select_top_risk_factors(risk_factors: list[RiskFactor]) -> list[RiskFactor]:
    """Select up to 3 top risk factors."""
    if not risk_factors:
        return []
    return risk_factors[:MAX_TOP_RISK_FACTORS]


def decide(
    assessment: RiskAssessment,
    beneficiary_status: BeneficiaryStatus,
    profile: CustomerProfile,
    request: FasterPaymentRequest,
) -> FraudDecision:
    """
    Produce a fraud decision based on the risk assessment, beneficiary status,
    customer profile, and payment request.
    """
    risk_score = assessment.riskScore
    threshold_override = False

    # 1. Beneficiary overrides (checked first)
    if beneficiary_status.flag == BeneficiaryFlag.MULE_LINKED:
        top_factors = _select_top_risk_factors(assessment.riskFactors)
        return FraudDecision(
            decision=Decision.BLOCK,
            riskScore=risk_score,
            topRiskFactors=top_factors,
            thresholdOverride=True,
        )

    if beneficiary_status.flag == BeneficiaryFlag.HIGH_RISK:
        if risk_score < HIGH_RISK_MINIMUM_SCORE:
            risk_score = HIGH_RISK_MINIMUM_SCORE
        threshold_override = True

    # 2. Dynamic threshold override
    if _exceeds_dynamic_threshold(request, profile):
        base_decision = _map_score_to_decision(risk_score)
        if base_decision == Decision.ALLOW:
            top_factors = _select_top_risk_factors(assessment.riskFactors)
            return FraudDecision(
                decision=Decision.REVIEW,
                riskScore=risk_score,
                topRiskFactors=top_factors,
                thresholdOverride=True,
            )
        threshold_override = True

    # 3. Map final score to decision
    decision = _map_score_to_decision(risk_score)

    # 4. Select top 3 risk factors
    top_factors = _select_top_risk_factors(assessment.riskFactors)

    return FraudDecision(
        decision=decision,
        riskScore=risk_score,
        topRiskFactors=top_factors,
        thresholdOverride=threshold_override,
    )
