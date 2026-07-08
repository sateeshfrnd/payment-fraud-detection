
payment-fraud-detection/localstack/
├── start-local.sh    # One-command full setup (LocalStack + backend + frontend)
├── stop-local.sh     # Tear down everything
└── seed-data.sh      # Seed test data independently

# To use
## Start everything
./payment-fraud-detection/localstack/start-local.sh

## Stop everything
./payment-fraud-detection/localstack/stop-local.sh

## Health Check
curl -s http://localhost:8000/health && echo "" && curl -s -o /dev/null -w "Frontend: HTTP %{http_code}" http://localhost:8501/

## Frontend
url -s -o /dev/null -w "Frontend: HTTP %{http_code}\n" http://localhost:8501/ 2>&1


The start-local.sh script handles the complete lifecycle:

1.Checks prerequisites (Python 3, pip, Docker, AWS CLI)
2.Installs Python packages (FastAPI, Streamlit, boto3, etc.)
3.Starts LocalStack in Docker
4.Creates DynamoDB table, S3 bucket, and EventBridge bus
5.Seeds test data (4 customer profiles + 3 beneficiary records)
6.Starts the FastAPI backend on port 8000 (with /docs for Swagger)
7.Starts the Streamlit frontend on port 8501

