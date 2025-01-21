# Glimpse

**Execute code snippets in secure, isolated environments via API**

Glimpse is a lightweight API service that securely runs user-submitted code in sandboxed environments. Demonstrates secure code execution patterns with safety constraints and multiple isolation strategies.

## Features

- **Language support**: Python, JS, C, Go, Kotlin (more to come)
- **Isolation**: Ephemeral containers or serverless functions per request
- **Security controls**:
  - Network access restrictions
  - Filesystem operation blocking
  - 30-second timeout enforcement
- **Architecture options**:
  - AWS Lambda deployment for serverless operation
  - Docker-based container pool for local development

## API Usage

**Endpoint**: `https://glimpse-7eir.onrender.com/run-code-lambda`

Example request:
```javascript
fetch("https://glimpse-7eir.onrender.com/run-code-lambda", {
  method: "POST",
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify({
    language: "py",
    code: 'print("Hello from Glimpse!")',
    input: ""
  }),
})
.then(response => response.json())
.then(data => console.log(data));
```

Example response:
```
{
  "statusCode": 200,
  "body": {
    "output": "Hello from Glimpse!\n",
    "error": null,
    "executionTime": null
  }
}
```


## Deployment

### AWS Lambda Configuration
Set environment variables:

```bash
AWS_ACCESS_KEY_ID=your_key
AWS_SECRET_ACCESS_KEY=your_secret
AWS_DEFAULT_REGION=your_region
LAMBDA_FUNCTION_NAME=your_lambda_function
```

Follow infrastructure deployment guide in /docs/infra.markdown

Start API server:

```bash
uvicorn api-lambda:app --host 0.0.0.0 --port 8000
```


### Docker-based Execution

Build container environment:

```bash
make build  # or ./setup.sh
```

Launch service:

```bash
uvicorn api-docker:app --host 0.0.0.0 --port 8000
```

## Security Constraints

- Maximum execution duration: 30 seconds
- Rate limiting: 1000 requests/hour per IP
- Restricted system access:
  - No persistent storage
  - No external network connectivity
  - Input limited to API parameters

## Architecture

Implements two isolation strategies:

### Serverless Execution
- Utilizes AWS Lambda for automatic scaling and isolation through AWS Firecracker microVMs

### Container Pooling
- Maintains pre-warmed Docker containers for rapid execution in development environments

## Core technologies:

- FastAPI (Python web server)
- Docker (Container runtime)
- AWS Lambda (Serverless compute)

## License

MIT License