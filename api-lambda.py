import os
import json
import boto3
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import PlainTextResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from dotenv import load_dotenv

from slowapi import Limiter
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded

# Load environment variables from .env
load_dotenv()

app = FastAPI()

# Load Lambda function name from environment
LAMBDA_FUNCTION_NAME = os.getenv("LAMBDA_FUNCTION_NAME")

# Configure AWS Lambda client
lambda_client = boto3.client(
    "lambda", region_name="us-east-1"
)  # Adjust region as needed

# CORS setup
origins = ["*"]
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Rate limiting setup
limiter = Limiter(key_func=get_remote_address)


@app.exception_handler(RateLimitExceeded)
async def rate_limit_handler(request, exc):
    return PlainTextResponse(str("Rate limit exceeded!"), status_code=429)


class CodeIn(BaseModel):
    language: str
    code: str
    input: str = None


@app.post("/run-code-lambda")
@limiter.limit("30/minute")
async def run_code_lambda(request: Request, code_in: CodeIn):
    """
    Executes user-submitted code using AWS Lambda.
    """
    payload = {
        "language": code_in.language,
        "code": code_in.code,
        "input": code_in.input,
    }

    try:
        # Check if LAMBDA_FUNCTION_NAME is set
        if not LAMBDA_FUNCTION_NAME:
            raise HTTPException(
                status_code=500, detail="LAMBDA_FUNCTION_NAME is not set."
            )

        # Invoke the Lambda function
        response = lambda_client.invoke(
            FunctionName=LAMBDA_FUNCTION_NAME,
            InvocationType="RequestResponse",
            Payload=json.dumps(payload),
        )

        # breakpoint()

        # Parse the Lambda response
        response_payload = json.load(response["Payload"])
        if response.get("FunctionError"):
            raise HTTPException(status_code=500, detail=response_payload.get("error"))

        return response_payload

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/")
async def root(request: Request):
    return {"message": "Welcome to the Glimpse API with Lambda integration!"}
