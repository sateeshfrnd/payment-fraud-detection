"""
Request validation for FasterPaymentRequest.
Validates all fields of a FasterPaymentRequest per Requirement.
Performs full-pass validation collecting ALL errors before returning.
"""
import re
from dataclasses import dataclass

from models import FasterPaymentRequest, ChannelType

ACCOUNT_NUMBER_PATTERN = re.compile(r"^\d{8}$")
SORT_CODE_PATTERN = re.compile(r"^\d{6}$")
MIN_AMOUNT = 0.01
MAX_AMOUNT = 1_000_000.00
REQUIRED_CURRENCY = "GBP"
MAX_PAYMENT_REFERENCE_LENGTH = 18


@dataclass
class ValidationError:
    field: str
    message: str


def validate_request(request: FasterPaymentRequest) -> list[ValidationError]:
    """Validate all fields of a FasterPaymentRequest. Returns list of errors (empty = valid)."""
    errors: list[ValidationError] = []

    # Required fields
    if request.debtorAccount is None:
        errors.append(ValidationError("debtorAccount", "debtorAccount is required"))
    if request.creditorAccount is None:
        errors.append(ValidationError("creditorAccount", "creditorAccount is required"))
    if request.amount is None:
        errors.append(ValidationError("amount", "amount is required"))
    if request.currency is None:
        errors.append(ValidationError("currency", "currency is required"))
    if request.channel is None:
        errors.append(ValidationError("channel", "channel is required"))

    # Debtor account
    if request.debtorAccount is not None:
        if not request.debtorAccount.accountNumber or not ACCOUNT_NUMBER_PATTERN.match(request.debtorAccount.accountNumber):
            errors.append(ValidationError(
                "debtorAccount.accountNumber",
                "debtorAccount accountNumber must be exactly 8 numeric digits",
            ))
        if not request.debtorAccount.sortCode or not SORT_CODE_PATTERN.match(request.debtorAccount.sortCode):
            errors.append(ValidationError(
                "debtorAccount.sortCode",
                "debtorAccount sortCode must be exactly 6 numeric digits",
            ))

    # Creditor account
    if request.creditorAccount is not None:
        if not request.creditorAccount.accountNumber or not ACCOUNT_NUMBER_PATTERN.match(request.creditorAccount.accountNumber):
            errors.append(ValidationError(
                "creditorAccount.accountNumber",
                "creditorAccount accountNumber must be exactly 8 numeric digits",
            ))
        if not request.creditorAccount.sortCode or not SORT_CODE_PATTERN.match(request.creditorAccount.sortCode):
            errors.append(ValidationError(
                "creditorAccount.sortCode",
                "creditorAccount sortCode must be exactly 6 numeric digits",
            ))

    # Amount
    if request.amount is not None:
        if request.amount < MIN_AMOUNT or request.amount > MAX_AMOUNT:
            errors.append(ValidationError("amount", "amount must be between 0.01 and 1000000.00"))

    # Currency
    if request.currency is not None:
        if request.currency != REQUIRED_CURRENCY:
            errors.append(ValidationError("currency", "currency must be GBP"))

    # Payment reference
    if request.paymentReference is not None:
        if len(request.paymentReference) > MAX_PAYMENT_REFERENCE_LENGTH:
            errors.append(ValidationError("paymentReference", "paymentReference must not exceed 18 characters"))

    # Channel type
    if request.channel is not None:
        if request.channel.type is None:
            errors.append(ValidationError(
                "channel.type",
                "channel type must be one of MOBILE, ONLINE_BANKING, API, BRANCH, PHONE",
            ))

    return errors
