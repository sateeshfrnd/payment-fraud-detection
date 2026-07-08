#!/bin/bash
###############################################################################
# Seed DynamoDB with test customer profiles and beneficiary records
#
# Creates test data for the Python FastAPI backend:
#   - 4 customer profiles (debtors) with varying transaction histories
#   - 3 beneficiary registry entries (NONE, HIGH_RISK, MULE_LINKED)
#
# Usage: ./payment-fraud-detection/localstack/seed-data.sh
#
# For a larger dataset (100 records), use the parent project's seed script:
#   ./localstack/seed-data.sh
###############################################################################
set -e

REGION="us-east-1"
ENDPOINT="http://localhost:4566"
TABLE_NAME="FraudDetection"

export AWS_ACCESS_KEY_ID=test
export AWS_SECRET_ACCESS_KEY=test
export AWS_DEFAULT_REGION=$REGION

echo "=== Seeding DynamoDB with test data ==="
echo ""

# Helper: put customer profile
put_profile() {
  local sort_code=$1
  local account_number=$2
  local mean_amount=$3
  local std_dev=$4
  local tx_count=$5
  local avg_session=$6

  aws --endpoint-url=$ENDPOINT dynamodb put-item \
    --table-name "$TABLE_NAME" \
    --item "{
      \"pk\": {\"S\": \"CUST#${sort_code}#${account_number}\"},
      \"sk\": {\"S\": \"PROFILE\"},
      \"meanAmount\": {\"N\": \"${mean_amount}\"},
      \"stdDevAmount\": {\"N\": \"${std_dev}\"},
      \"transactionCount90d\": {\"N\": \"${tx_count}\"},
      \"devices\": {\"L\": [{\"S\": \"device-001\"}, {\"S\": \"device-002\"}]},
      \"locations\": {\"L\": [{\"S\": \"51.5074,-0.1278\"}, {\"S\": \"51.4545,-2.5879\"}]},
      \"avgSessionDuration\": {\"N\": \"${avg_session}\"},
      \"lastUpdated\": {\"S\": \"2026-06-01T10:00:00Z\"}
    }" --no-cli-pager 2>/dev/null
}

# Helper: put beneficiary
put_beneficiary() {
  local sort_code=$1
  local account_number=$2
  local flag=$3
  local reason=$4

  aws --endpoint-url=$ENDPOINT dynamodb put-item \
    --table-name "$TABLE_NAME" \
    --item "{
      \"pk\": {\"S\": \"BENE#${sort_code}#${account_number}\"},
      \"sk\": {\"S\": \"STATUS\"},
      \"flag\": {\"S\": \"${flag}\"},
      \"lastUpdated\": {\"S\": \"2026-05-15T08:00:00Z\"},
      \"reason\": {\"S\": \"${reason}\"}
    }" --no-cli-pager 2>/dev/null
}

echo "--- Creating customer profiles ---"

# Low-risk customer: regular spending, high tx count
put_profile "101010" "10000001" "350" "80" "120" "150000"
echo "✓ Low-risk debtor: 101010 / 10000001 (mean £350, 120 txns)"

# Medium-risk customer: moderate spending, fewer transactions
put_profile "202020" "20000001" "800" "250" "35" "90000"
echo "✓ Medium-risk debtor: 202020 / 20000001 (mean £800, 35 txns)"

# High-value customer: large regular payments
put_profile "303030" "30000001" "8000" "3000" "80" "200000"
echo "✓ High-value debtor: 303030 / 30000001 (mean £8000, 80 txns)"

# New customer: very few transactions
put_profile "404040" "40000001" "150" "50" "3" "45000"
echo "✓ New customer: 404040 / 40000001 (mean £150, 3 txns)"

echo ""
echo "--- Creating beneficiary records ---"

# Clean creditor
put_beneficiary "505050" "50000001" "NONE" "No adverse information"
echo "✓ Clean creditor: 505050 / 50000001 (NONE)"

# High-risk creditor
put_beneficiary "606060" "60000001" "HIGH_RISK" "Multiple fraud reports received"
echo "✓ High-risk creditor: 606060 / 60000001 (HIGH_RISK)"

# Mule-linked creditor
put_beneficiary "707070" "70000001" "MULE_LINKED" "Linked to known money mule network"
echo "✓ Mule-linked creditor: 707070 / 70000001 (MULE_LINKED)"

echo ""
echo "=== Seed Complete ==="
echo ""
echo "Test scenarios to try:"
echo "  • Low-risk debtor (101010/10000001) → clean creditor (505050/50000001), £150, MATCH → ALLOW"
echo "  • Medium debtor (202020/20000001) → clean creditor, £5000, MATCH → REVIEW"
echo "  • New customer (404040/40000001) → high-risk creditor (606060/60000001), £9500, NO_MATCH → BLOCK"
echo "  • Any debtor → mule creditor (707070/70000001), any amount → BLOCK"
