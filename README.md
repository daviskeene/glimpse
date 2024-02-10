# Glimpse

Glimpse is a microservice that allows for remote code execution, written in Python.

Current list of supported languages:
- Java
- C++
- Python
- C
- JavaScript
- GoLang

## Getting Started

Glimpse is not yet deployed, but will be soon. In the meantime, you can spin it up yourself locally.

1. Run the following setup script: `chmod +x setup.sh && ./setup.sh`. This will install all necessary Python dependencies and build the Docker image.
2. To run the FastAPI app, use the following command: `python3 -m uvicorn api:app --host 0.0.0.0 --port 8000 --workers <int:num_workers>`.
    - `num_workers` will decide the number of web workers that are running the API in parallel. When developing locally, no more than 2 are needed.
3. Send a request to the endpoint like so:

```javascript
fetch('<endpoint_url>/run-code-pool', {
    method: 'POST',
    headers: {
        "Content-Type": "application/json"
    },
    body: JSON.stringify({
        "language": "py", // also accepts "java", "js", "cpp", "c", "go"
        "code": "print(\"Hello, world!\")",
        "input": ""  // optional parameter
    })
}).then((resp) => resp.json())
.then((data) => console.log(data));
```

Or use our friendly neighborhood cURL CLI tool:

```bash
curl -X POST '<endpoint_url>/run-code-pool' \
    -H 'Content-Type: application/json' \
    -d '{"language": "py", "code": "print(\"Hello, world!\")", "input": ""}'
```

The output from the endpoint will be as follows:

```
{
    "output": "Hello, world!\n",
    "error": "",
    "language": "py",
    "info": "python3 --version"
}
```

## How It Works

Glimpse allows code to be executed via a web request. You can run code and display code results in environment like Node, in a React application, etc. It works by sending instructions to a Docker container about how to compile and/or execute code coming in, carrying out those instructions, and saving the result before replacing the code-contaminated container.

<details>
<summary>v2.</summary>

The current iteration of Glimpse recognizes that untrusted code should not be ran outside of a containerized environment. What's more, code submissions should run in their own container.

We now maintain a scalable container "pool" of pre-warmed containers that are all able to execute code in any of the supported languages. When a code submission is submitted via our endpoint, a few things happen:

- A pre-warmed container is selected from the pool, and we create a record of that submission in the container.
- That code file is executed in the container, and the output is recorded.
- That container is discarded, and a new one takes its place.

</details>

<details>
<summary>v1.</summary>

The first iteration of Glimpse ran in a single Docker container, which has all the necessary software installed to compile and run files from supported languages.

When a request was made to Lantern's `run_code` endpoint, the corresponding method `run_code` was called, and the following steps occurred in order:
1. A submission file was generated with a unique UUID and the proper extension.
2. A set of compilation and execution command line arguments were generated, instructing the container how to execute the `code` parameter that was passed in.
3. The code was compiled (if a compilation step is necessary) and executed, and the resulting std_out and std_err streams were captured and returned as a Response.

Glimpse takes advantage of FastAPI's support for async Python to compile and execute code processing requests in "parallel" (thanks, GIL).
</details>

## Limitations

Glimpse is not meant to be used to run I/O operations in most languages. If one were to try to run the command `input()` with Glimpse, it would eventually timeout.
All I/O interactions must be spoofed on the client-side and inputs are passed as a value array once code execution can continue.