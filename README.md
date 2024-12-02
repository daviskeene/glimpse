# Glimpse

A simple service that lets you run code through an API. Want to execute some Python or JavaScript without setting up a whole environment? Glimpse has got you covered! 🚀

## What is this?

Glimpse is a service that takes code you send it and runs it in a safe, isolated environment. Think of it like running code on your computer, but in the cloud. It's perfect for:

- Building coding playgrounds
- Running code examples in documentation
- Testing quick code snippets
- Teaching programming concepts

## Try it out!

The service is running at `https://glimpse-7eir.onrender.com`. Here's a quick example:

```javascript
// Send some code to run
fetch("https://glimpse-7eir.onrender.com/run-code-lambda", {
  method: "POST",
  headers: {
    "Content-Type": "application/json",
  },
  body: JSON.stringify({
    language: "py",
    code: 'print("Hello from Glimpse!")',
    input: "", // optional: for programs that need input
  }),
})
  .then((response) => response.json())
  .then((data) => console.log(data));
```

You'll get back something like this:

```javascript
{
  "statusCode": 200,
  "body": {
    "output": "Hello from Glimpse!\n",
    "error": null,
    "executionTime": null  // not yet implemented
  }
}
```

## Setting it up yourself

There are two ways to run Glimpse:

### 1. AWS Lambda Mode (Recommended)

This uses AWS Lambda to run the code (what the production version does). You'll need to:

1. Create a `.env` file with your AWS credentials:

```bash
DOCKER_IMAGE=glimpse
LAMBDA_FUNCTION_NAME=your_lambda_function
AWS_ACCESS_KEY_ID=your_key
AWS_SECRET_ACCESS_KEY=your_secret
AWS_DEFAULT_REGION=your_region
```

2. Follow the steps in [here](/docs/infra.markdown) to upload the image to ECR + deploy the lambda.

3. Run the server:

```bash
python3 -m uvicorn api-lambda:app --host 0.0.0.0 --port 8000 --reload
```

### 2. Docker Pool Mode

This runs code in a pool of Docker containers. Simpler to set up, but needs more resources:

1. Set up Docker (make sure the daemon is running) and run:

```bash
# Install dependencies and build the docker image
make build
# or
./setup.sh

# Run the service
python3 -m uvicorn api-docker:app --host 0.0.0.0 --port 8000 --reload
```

## Good to know

- Currently supports Python and JavaScript
- Each request has a 30-second timeout
- Rate limited to 1000 requests per hour per IP
- Can't do file operations or network calls (for security reasons)
- Need to provide input through the API (no interactive `input()` calls)

## But why?

Ever wanted to build something that needs to run user-submitted code? Maybe a coding tutorial website or a documentation playground? Glimpse makes that easy without having to worry about all the security and isolation stuff.

## Want to help?

Feel free to open issues or submit PRs! This is a fun project and I'm always looking to make it better.

## Credits

Built with:

- FastAPI + Python3
- AWS Lambda (for the serverless goodness)
- Docker (for the v1 container pool magic)

## License

MIT License - do whatever you want with it! Just don't blame us if something goes wrong. 😉
