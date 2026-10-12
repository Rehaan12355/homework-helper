#!/bin/sh
# Started by the AWS Lambda Web Adapter; it forwards Function URL requests here.
exec python -m uvicorn homework_helper.cloud:mcp_app --host 127.0.0.1 --port "${AWS_LWA_PORT:-8080}"
