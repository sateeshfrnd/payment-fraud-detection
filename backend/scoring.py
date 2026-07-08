"""
Risk scoring engine and component scorers.

Four independent scorers each contribute 0-25 points:
- AmountScorer: deviation from historical mean 
- CopScorer: Confirmation of Payee result
- BehaviouralScorer: session duration vs average
- ChannelScorer: unknown device, geolocation, PHONE channel
"""

import math
import re
from typing import Optional

from models import (
    BeneficiaryStatus,
    Channel,
    ChannelType,
    ConfirmationOfPayee,
    CopResult,
    CustomerProfile,
    FasterPaymentRequest,
    GeoLocation,
    RiskAssessment,
    RiskFactor,
    ScorerResult,
)


# ---------------------------------------------------------------------------
# Amount Scorer
# ---------------------------------------------------------------------------

_AMOUNT_MAX_SCORE = 25
_AMOUNT_POINTS_PER_STDDEV = 10
_AMOUNT_MIN_TRANSACTIONS = 5
_AMOUNT_DEFAULT_THRESHOLD = 500.0
_AMOUNT_DEFAULT_STDDEV = 166.67  # DEFAULT_THRESHOLD / 3
_AMOUNT_STDDEV_MULTIPLIER = 3


def score_amount(request: FasterPaymentRequest, profile: CustomerProfile) -> ScorerResult:
    """
    Score amount risk based on deviation from the debtor's historical mean.
    
    When the debtor has fewer than 5 transactions in the most recent 90 days,
    a default threshold of £500 is applied (Requirement 3.4).

    When the amount exceeds mean + 3σ, the score is calculated as:
    min(25, 10 × floor((amount - mean) / stddev)) (Requirement 3.1).

    """
    amount = request.amount

    if profile.transactionCount90d < _AMOUNT_MIN_TRANSACTIONS:
        mean = _AMOUNT_DEFAULT_THRESHOLD
        stddev = _AMOUNT_DEFAULT_STDDEV
    else:
        mean = profile.meanAmount
        stddev = profile.stdDevAmount

    # Guard against zero or negative stddev
    if stddev <= 0:
        if amount > mean:
            return ScorerResult(
                score=_AMOUNT_MAX_SCORE,
                explanation=f"Amount £{amount:.2f} exceeds mean £{mean:.2f} with zero variance",
            )
        return ScorerResult(
            score=0,
            explanation=f"Amount £{amount:.2f} within expected range (mean £{mean:.2f})",
        )

    threshold = mean + (_AMOUNT_STDDEV_MULTIPLIER * stddev)

    if amount <= threshold:
        return ScorerResult(
            score=0,
            explanation=f"Amount £{amount:.2f} within {_AMOUNT_STDDEV_MULTIPLIER}σ of mean £{mean:.2f}",
        )

    # Amount exceeds mean + 3σ
    deviations = (amount - mean) / stddev
    raw_score = _AMOUNT_POINTS_PER_STDDEV * int(math.floor(deviations))
    score = min(_AMOUNT_MAX_SCORE, raw_score)

    if profile.transactionCount90d < _AMOUNT_MIN_TRANSACTIONS:
        explanation = (
            f"Amount £{amount:.2f} exceeds default threshold £{_AMOUNT_DEFAULT_THRESHOLD:.2f} "
            f"({deviations:.1f}σ above mean, low history)"
        )
    else:
        explanation = f"Amount £{amount:.2f} is {deviations:.1f}σ above historical mean £{mean:.2f}"

    return ScorerResult(score=score, explanation=explanation)


# ---------------------------------------------------------------------------
# CoP Scorer
# ---------------------------------------------------------------------------


def score_cop(request: FasterPaymentRequest, profile: CustomerProfile) -> ScorerResult:
    """Score risk based on Confirmation of Payee result."""
    cop = request.confirmationOfPayee

    if cop is None or cop.result is None:
        return ScorerResult(score=15, explanation="CoP data absent or null; elevated uncertainty score applied")

    match cop.result:
        case CopResult.MATCH:
            return ScorerResult(score=0, explanation="CoP result MATCH; payee name confirmed, no risk")
        case CopResult.CLOSE_MATCH:
            return ScorerResult(score=10, explanation="CoP result CLOSE_MATCH; minor name discrepancy detected")
        case CopResult.NO_MATCH:
            return ScorerResult(score=22, explanation="CoP result NO_MATCH; payee name does not match account holder")
        case CopResult.NOT_AVAILABLE:
            return ScorerResult(score=15, explanation="CoP result NOT_AVAILABLE; service unavailable, elevated uncertainty")


# ---------------------------------------------------------------------------
# Behavioural Scorer
# ---------------------------------------------------------------------------

_BEHAV_MAX_SCORE = 25
_BEHAV_MIN_SHORT_SESSION_SCORE = 10
_BEHAV_SHORT_SESSION_THRESHOLD = 0.50


def _parse_duration_to_ms(duration_str: Optional[str]) -> Optional[float]:
    """Parse an ISO-8601 duration string (e.g. 'PT120S', 'PT2M') to milliseconds."""
    if not duration_str:
        return None
    # Handle common patterns: PT{n}S, PT{n}M, PT{n}H, PT{m}M{n}S
    pattern = re.compile(r"PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+(?:\.\d+)?)S)?", re.IGNORECASE)
    m = pattern.match(duration_str)
    if not m:
        return None
    hours = float(m.group(1) or 0)
    minutes = float(m.group(2) or 0)
    seconds = float(m.group(3) or 0)
    total_ms = (hours * 3600 + minutes * 60 + seconds) * 1000
    return total_ms if total_ms > 0 else None


def score_behavioural(request: FasterPaymentRequest, profile: CustomerProfile) -> ScorerResult:
    """Score behavioural risk based on session duration vs average."""
    channel = request.channel
    if channel is None:
        return ScorerResult(score=0, explanation="No channel data available for behavioural scoring")

    session_ms = _parse_duration_to_ms(channel.sessionDuration)
    if session_ms is None:
        return ScorerResult(score=0, explanation="No session duration available for behavioural scoring")

    avg_session_ms = profile.avgSessionDurationMs
    if avg_session_ms <= 0:
        return ScorerResult(score=0, explanation="No session history available for comparison")

    ratio = session_ms / avg_session_ms

    if ratio >= _BEHAV_SHORT_SESSION_THRESHOLD:
        return ScorerResult(
            score=0,
            explanation=(
                f"Session duration {session_ms:.0f}ms is {ratio * 100:.0f}% of "
                f"average {avg_session_ms:.0f}ms (above 50% threshold)"
            ),
        )

    # Session is below 50% of average — score proportionally
    severity_factor = 1.0 - (ratio / _BEHAV_SHORT_SESSION_THRESHOLD)
    score = _BEHAV_MIN_SHORT_SESSION_SCORE + round(severity_factor * (_BEHAV_MAX_SCORE - _BEHAV_MIN_SHORT_SESSION_SCORE))
    score = min(_BEHAV_MAX_SCORE, max(_BEHAV_MIN_SHORT_SESSION_SCORE, score))

    return ScorerResult(
        score=score,
        explanation=(
            f"Session duration {session_ms:.0f}ms is {ratio * 100:.0f}% of "
            f"average {avg_session_ms:.0f}ms (below 50% threshold)"
        ),
    )


# ---------------------------------------------------------------------------
# Channel Scorer
# ---------------------------------------------------------------------------

_CHAN_UNKNOWN_DEVICE_SCORE = 10
_CHAN_UNKNOWN_LOCATION_SCORE = 15
_CHAN_PHONE_CHANNEL_SCORE = 5
_CHAN_MAX_SCORE = 25
_CHAN_DISTANCE_THRESHOLD_KM = 50.0
_EARTH_RADIUS_KM = 6371.0


def _haversine_distance(loc1: GeoLocation, loc2: GeoLocation) -> float:
    """Calculate great-circle distance in km between two geographic coordinates."""
    lat1_rad = math.radians(loc1.latitude)
    lat2_rad = math.radians(loc2.latitude)
    delta_lat = math.radians(loc2.latitude - loc1.latitude)
    delta_lon = math.radians(loc2.longitude - loc1.longitude)

    a = (math.sin(delta_lat / 2) ** 2
         + math.cos(lat1_rad) * math.cos(lat2_rad)
         * math.sin(delta_lon / 2) ** 2)
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return _EARTH_RADIUS_KM * c


def _is_unknown_device(channel: Optional[Channel], profile: CustomerProfile) -> bool:
    """Check if the device is not in the customer's known devices."""
    if channel is None or not channel.deviceId:
        return True
    if not profile.knownDevices:
        return True
    return channel.deviceId not in profile.knownDevices


def _is_unknown_location(channel: Optional[Channel], profile: CustomerProfile) -> bool:
    """Check if the geolocation is more than 50km from all known locations."""
    if channel is None or channel.geoLocation is None:
        return False  # No location data → don't penalise
    if not profile.knownLocations:
        return True  # No history → treat as unknown
    for known in profile.knownLocations:
        dist = _haversine_distance(channel.geoLocation, known)
        if dist <= _CHAN_DISTANCE_THRESHOLD_KM:
            return False
    return True


def score_channel(request: FasterPaymentRequest, profile: CustomerProfile) -> ScorerResult:
    """Score channel/device/geolocation risk."""
    total_score = 0
    factors: list[str] = []

    if _is_unknown_device(request.channel, profile):
        total_score += _CHAN_UNKNOWN_DEVICE_SCORE
        factors.append("unknown device")

    if _is_unknown_location(request.channel, profile):
        total_score += _CHAN_UNKNOWN_LOCATION_SCORE
        factors.append("location >50km from known locations")

    if request.channel and request.channel.type == ChannelType.PHONE:
        total_score += _CHAN_PHONE_CHANNEL_SCORE
        factors.append("PHONE channel")

    total_score = min(total_score, _CHAN_MAX_SCORE)

    if not factors:
        explanation = f"Channel risk: no risk factors identified, score={total_score}"
    else:
        explanation = f"Channel risk (score={total_score}): {', '.join(factors)}"
        if len(explanation) > 200:
            explanation = explanation[:197] + "..."

    return ScorerResult(score=total_score, explanation=explanation)


# ---------------------------------------------------------------------------
# Risk Scoring Engine
# ---------------------------------------------------------------------------


def compute_risk_assessment(
    request: FasterPaymentRequest,
    profile: CustomerProfile,
    beneficiary_status: BeneficiaryStatus,
) -> RiskAssessment:
    """
    Compose all four scorers and produce a composite RiskAssessment.
    Each scorer contributes [0, 25]; composite range is [0, 100].
    """
    amount_result = score_amount(request, profile)
    cop_result = score_cop(request, profile)
    behavioural_result = score_behavioural(request, profile)
    channel_result = score_channel(request, profile)

    composite_score = (
        amount_result.score + cop_result.score + behavioural_result.score + channel_result.score
    )

    risk_factors: list[RiskFactor] = []
    if amount_result.score > 0:
        risk_factors.append(RiskFactor(category="amount", explanation=amount_result.explanation))
    if cop_result.score > 0:
        risk_factors.append(RiskFactor(category="cop", explanation=cop_result.explanation))
    if behavioural_result.score > 0:
        risk_factors.append(RiskFactor(category="behavioural", explanation=behavioural_result.explanation))
    if channel_result.score > 0:
        risk_factors.append(RiskFactor(category="channel", explanation=channel_result.explanation))

    return RiskAssessment(
        riskScore=composite_score,
        amountScore=amount_result.score,
        copScore=cop_result.score,
        behaviouralScore=behavioural_result.score,
        channelScore=channel_result.score,
        riskFactors=risk_factors,
    )
