"""
DynamoDB repository layer.

Reads customer profiles and beneficiary statuses from the FraudDetection
single-table design. Writes audit records after decisions.

"""

import json
import logging
import os
from datetime import datetime, timezone
from typing import Optional

import boto3
from botocore.config import Config as BotoConfig

from models import (
    BeneficiaryFlag,
    BeneficiaryStatus,
    CustomerProfile,
    Decision,
    FraudDecisionResponse,
    GeoLocation,
    RiskFactor,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

TABLE_NAME = os.environ.get("FRAUD_DETECTION_TABLE", "FraudDetection")
AUDIT_BUCKET = os.environ.get("AUDIT_BUCKET_NAME", "fraud-audit-archive")
EVENT_BUS_NAME = os.environ.get("EVENT_BUS_NAME", "fraud-detection")
AWS_REGION = os.environ.get("AWS_DEFAULT_REGION", "us-east-1")
ENDPOINT_URL = os.environ.get("AWS_ENDPOINT_URL", "http://localhost:4566")


def _get_boto_kwargs() -> dict:
    """Build common boto3 client kwargs for LocalStack or real AWS."""
    kwargs = {"region_name": AWS_REGION}
    if ENDPOINT_URL:
        kwargs["endpoint_url"] = ENDPOINT_URL
        kwargs["aws_access_key_id"] = os.environ.get("AWS_ACCESS_KEY_ID", "test")
        kwargs["aws_secret_access_key"] = os.environ.get("AWS_SECRET_ACCESS_KEY", "test")
    return kwargs


def _dynamodb_client():
    return boto3.client("dynamodb", **_get_boto_kwargs())


def _eventbridge_client():
    return boto3.client("events", **_get_boto_kwargs())


def _s3_client():
    return boto3.client("s3", **_get_boto_kwargs())


# ---------------------------------------------------------------------------
# Customer Profile Repository
# ---------------------------------------------------------------------------


def get_customer_profile(sort_code: str, account_number: str) -> Optional[CustomerProfile]:
    """
    Retrieve a customer profile from DynamoDB.
    Key: pk=CUST#{sortCode}#{accountNumber}, sk=PROFILE
    Returns None if not found.
    """
    client = _dynamodb_client()
    pk = f"CUST#{sort_code}#{account_number}"

    try:
        response = client.get_item(
            TableName=TABLE_NAME,
            Key={"pk": {"S": pk}, "sk": {"S": "PROFILE"}},
        )
    except Exception as e:
        logger.warning("Failed to load customer profile for %s/%s: %s", sort_code, account_number, e)
        return None

    item = response.get("Item")
    if not item:
        return None

    # Parse locations from "lat,lng" string list
    known_locations: list[GeoLocation] = []
    locations_attr = item.get("locations", {}).get("L", [])
    for loc_item in locations_attr:
        loc_str = loc_item.get("S", "")
        parts = loc_str.split(",")
        if len(parts) == 2:
            try:
                known_locations.append(GeoLocation(latitude=float(parts[0]), longitude=float(parts[1])))
            except ValueError:
                pass

    # Parse devices
    known_devices: list[str] = []
    devices_attr = item.get("devices", {}).get("L", [])
    for dev_item in devices_attr:
        dev_str = dev_item.get("S", "")
        if dev_str:
            known_devices.append(dev_str)

    return CustomerProfile(
        sortCode=sort_code,
        accountNumber=account_number,
        meanAmount=float(item.get("meanAmount", {}).get("N", "0")),
        stdDevAmount=float(item.get("stdDevAmount", {}).get("N", "0")),
        transactionCount90d=int(item.get("transactionCount90d", {}).get("N", "0")),
        knownDevices=known_devices,
        knownLocations=known_locations,
        avgSessionDurationMs=float(item.get("avgSessionDuration", {}).get("N", "0")),
        lastUpdated=item.get("lastUpdated", {}).get("S"),
    )


# ---------------------------------------------------------------------------
# Beneficiary Registry Repository
# ---------------------------------------------------------------------------


def get_beneficiary_status(sort_code: str, account_number: str) -> BeneficiaryStatus:
    """
    Retrieve a beneficiary's risk status from DynamoDB.
    Key: pk=BENE#{sortCode}#{accountNumber}, sk=STATUS
    Returns BeneficiaryStatus with flag=NONE if not found.
    """
    client = _dynamodb_client()
    pk = f"BENE#{sort_code}#{account_number}"

    try:
        response = client.get_item(
            TableName=TABLE_NAME,
            Key={"pk": {"S": pk}, "sk": {"S": "STATUS"}},
        )
    except Exception as e:
        logger.warning("Failed to load beneficiary status for %s/%s: %s", sort_code, account_number, e)
        return BeneficiaryStatus(flag=BeneficiaryFlag.NONE)

    item = response.get("Item")
    if not item:
        return BeneficiaryStatus(flag=BeneficiaryFlag.NONE)

    flag_str = item.get("flag", {}).get("S", "NONE")
    try:
        flag = BeneficiaryFlag(flag_str)
    except ValueError:
        flag = BeneficiaryFlag.NONE

    last_updated = item.get("lastUpdated", {}).get("S")
    return BeneficiaryStatus(flag=flag, lastUpdated=last_updated)


# ---------------------------------------------------------------------------
# Audit Record Writer
# ---------------------------------------------------------------------------


def write_audit_record(
    request_data: dict,
    response: FraudDecisionResponse,
) -> None:
    """
    Write the decision audit record to DynamoDB and archive to S3.
    Mirrors AuditLogHandler logic. Fire-and-forget (errors are logged, not raised).
    """
    try:
        client = _dynamodb_client()
        message_id = response.messageId
        timestamp = response.timestamp

        debtor = request_data.get("debtorAccount", {})
        creditor = request_data.get("creditorAccount", {})

        item = {
            "pk": {"S": f"AUDIT#{message_id}"},
            "sk": {"S": "DECISION"},
            "timestamp": {"S": timestamp},
            "debtorAccount": {"S": f"{debtor.get('sortCode', '')}#{debtor.get('accountNumber', '')}"},
            "creditorAccount": {"S": f"{creditor.get('sortCode', '')}#{creditor.get('accountNumber', '')}"},
            "amount": {"N": str(request_data.get("amount", 0))},
            "riskScore": {"N": str(response.riskScore)},
            "decision": {"S": response.decision.value},
            "amountScore": {"N": str(response.breakdown.amountScore)},
            "copScore": {"N": str(response.breakdown.copScore)},
            "behaviouralScore": {"N": str(response.breakdown.behaviouralScore)},
            "channelScore": {"N": str(response.breakdown.channelScore)},
            "gsiPk": {"S": f"DECISION#{response.decision.value}"},
            "gsiSk": {"S": timestamp},
        }

        if response.riskFactors:
            item["riskFactors"] = {"L": [{"S": rf.category} for rf in response.riskFactors]}
            item["explanations"] = {"L": [{"S": rf.explanation} for rf in response.riskFactors]}

        client.put_item(TableName=TABLE_NAME, Item=item)
        logger.info("Audit record written for messageId=%s", message_id)

    except Exception as e:
        logger.error("Failed to write audit record: %s", e)

    # Archive to S3
    try:
        s3 = _s3_client()
        # Parse timestamp for S3 key path
        date_parts = timestamp[:10].split("-") if timestamp else ["2026", "01", "01"]
        s3_key = f"decisions/{date_parts[0]}/{date_parts[1]}/{date_parts[2]}/{message_id}.json"

        archive_data = {
            "messageId": message_id,
            "timestamp": timestamp,
            "debtorAccount": debtor,
            "creditorAccount": creditor,
            "amount": request_data.get("amount", 0),
            "riskScore": response.riskScore,
            "decision": response.decision.value,
            "breakdown": response.breakdown.model_dump(),
            "riskFactors": [rf.model_dump() for rf in response.riskFactors],
        }

        s3.put_object(
            Bucket=AUDIT_BUCKET,
            Key=s3_key,
            Body=json.dumps(archive_data),
            ContentType="application/json",
        )
        logger.info("Archived to S3: %s", s3_key)

    except Exception as e:
        logger.error("Failed to archive to S3: %s", e)


# ---------------------------------------------------------------------------
# Event Publisher
# ---------------------------------------------------------------------------


def publish_decision_event(request_data: dict, response: FraudDecisionResponse) -> None:
    """
    Publish a DecisionMade event to EventBridge. Fire-and-forget.
    Mirrors EventBridgeEventPublisher.
    """
    try:
        client = _eventbridge_client()

        debtor = request_data.get("debtorAccount", {})
        creditor = request_data.get("creditorAccount", {})

        detail = {
            "messageId": response.messageId,
            "timestamp": response.timestamp,
            "debtorAccount": debtor,
            "creditorAccount": creditor,
            "amount": request_data.get("amount", 0),
            "riskScore": response.riskScore,
            "decision": response.decision.value,
            "amountScore": response.breakdown.amountScore,
            "copScore": response.breakdown.copScore,
            "behaviouralScore": response.breakdown.behaviouralScore,
            "channelScore": response.breakdown.channelScore,
            "riskFactors": [rf.model_dump() for rf in response.riskFactors],
        }

        client.put_events(
            Entries=[
                {
                    "EventBusName": EVENT_BUS_NAME,
                    "Source": "com.frauddetection",
                    "DetailType": "DecisionMade",
                    "Detail": json.dumps(detail),
                }
            ]
        )
        logger.info("Published DecisionMade event for messageId=%s", response.messageId)

    except Exception as e:
        logger.error("Failed to publish event: %s", e)
