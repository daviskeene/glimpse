import os

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import PlainTextResponse
from fastapi.middleware.cors import CORSMiddleware
from motor.motor_asyncio import AsyncIOMotorClient
from dotenv import load_dotenv
from pydantic import BaseModel

from slowapi import Limiter
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded

from glimpse import run_code, run_code_pool
from containers import ContainerPool

app = FastAPI()
load_dotenv()  # load environment variables on API startup

# TODO: Remove wildcard and replace with valid urls
# after hosting
origins = ["*"]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Initialize the container pool
container_pool = ContainerPool(
    pool_size=2, image=os.getenv("DOCKER_IMAGE", "glimpse")
)

# Rate limiting
limiter = Limiter(key_func=get_remote_address)

@app.exception_handler(RateLimitExceeded)
async def rate_limit_handler(request, exc):
    return PlainTextResponse(str("Rate limit exceeded!"), status_code=429)

@app.on_event("startup")
async def start_pool():
    # Start Container pool
    container_pool.warm_up()
    pass

@app.on_event("shutdown")
async def clean_pool():
    # Clean out docker containers from container pool
    container_pool.shutdown_pool()
    pass

class CodeIn(BaseModel):
    language: str
    code: str
    input: str = None

@app.post("/run-code-local")
async def run_code_endpoint(code_in: CodeIn):
    """
    Makes a call to `run_code` with request parameters.
    Requires JWT Bearer Token Authentication (prevents against code being ran from non-authenticated client)
    """
    try:
        result = await run_code(code_in.language, code_in.code, code_in.input)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))
    return result


@app.post("/run-code-pool")
@limiter.limit("30/minute")
async def run_code_endpoint(request: Request, code_in: CodeIn):
    """
    Makes a call to `run_code` with request parameters, without authenticated protection.
    """
    try:
        result = await run_code_pool(
            code_in.language, code_in.code, code_in.input, container_pool=container_pool
        )
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))
    return result

@app.get("/")
async def root(request: Request):
    url_list = [
        {"path": route.path, "name": route.name} for route in request.app.routes
    ]
    return {"paths": url_list}
