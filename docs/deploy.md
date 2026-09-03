# Deploying Glimpse

Three shapes are supported. In every case the API is the same FastAPI app; only
`GLIMPSE_RUNNER` changes. The public instance uses shape 1; shapes 2 and 3 remain for
serverless deployments (they were the original production path and are no longer needed
for the demo).

## 1. A public instance on one VM (recommended)

This is how the free instance behind the demo runs: one small, **dedicated, disposable**
VM with Docker, the API and sandbox image from `docker-compose.yml`, Caddy for TLS, and
Cloudflare's free tier in front. Fixed cost (≈ €4–7/month), no cold starts, and abuse can
only ever saturate the box — it cannot run up a bill.

Sizing: 2 vCPU / 4 GB (Hetzner CAX11 arm64 or CX22 x86, DigitalOcean's $12 droplet, or
Oracle Cloud's free ARM tier if you can get capacity) comfortably runs `pool=2,
max_concurrency=4` at 512 MiB per sandbox — several runs per second. Scale up the instance
before scaling out.

### 1. Provision the VM (one CLI command)

Ubuntu 24.04, nothing else on it. Because the API needs the Docker socket (root-equivalent
on the host), treat the machine as disposable: no cloud credentials, no SSH keys that open
anything else, no other services.

`deploy/cloud-init.yaml` is provider-agnostic cloud-init: it installs Docker, opens only
SSH/80/443, clones the repo and runs `make prod`. Substitute the placeholders and pass it
as user data:

```sh
sed -e 's/__GLIMPSE_DOMAIN__/api.glimpse.example.com/' \
    -e 's#__GLIMPSE_REPO__#https://github.com/daviskeene/glimpse#' \
    deploy/cloud-init.yaml > /tmp/glimpse-user-data.yaml
```

**DigitalOcean** (`doctl auth init`; ~$24/mo for 2 vCPU / 4 GB):

```sh
doctl compute ssh-key import glimpse --public-key-file ~/.ssh/id_ed25519.pub
doctl compute droplet create glimpse-1 --image ubuntu-24-04-x64 --size s-2vcpu-4gb \
    --region nyc3 --ssh-keys <fingerprint-from-previous-command> \
    --user-data-file /tmp/glimpse-user-data.yaml --wait
```

**Hetzner** (`hcloud context create glimpse`; ~€8/mo `cpx21` US, ~€4.5 ARM `cax11` EU-only):

```sh
hcloud ssh-key create --name glimpse --public-key-from-file ~/.ssh/id_ed25519.pub
hcloud server create --name glimpse-1 --image ubuntu-24.04 --type cpx21 --location ash \
    --ssh-key glimpse --user-data-from-file /tmp/glimpse-user-data.yaml
```

The first boot takes ~10 minutes (image builds); follow it with
`ssh root@<ip> tail -f /var/log/cloud-init-output.log`. Scaling out later is the same
command with `glimpse-2` plus a load balancer or a second DNS record. Provisioning by
hand instead: run the steps you can read in `deploy/cloud-init.yaml`, then `make prod`.

### 2. Configuration

Cloud-init already wrote `/opt/glimpse/.env` (domain, rate limits, concurrency) and ran
`make prod`; edit that file and re-run `make prod` to change anything. On a hand-built box
create it yourself — the keys are in the cloud-init file and `.env.example`.

`make prod` runs `docker compose -f docker-compose.yml -f deploy/docker-compose.prod.yml
up -d --build`: the base file builds the sandbox image and the API (bound to
`127.0.0.1:8000` only); the overlay adds Caddy on :80/:443 in front of it, turns on
`GLIMPSE_TRUST_PROXY` + the global rate limit, and rotates container logs. Everything
restarts on reboot.

### 3. DNS and Cloudflare

1. Add an `A` (and `AAAA`) record for the hostname pointing at the VM, **proxied**
   (orange cloud). Cloudflare's free plan gives DDoS protection, hides the origin IP and
   terminates TLS at the edge.
2. SSL/TLS mode: **Full (strict)**. Caddy obtains a Let's Encrypt certificate through the
   proxy with the HTTP-01 challenge (Cloudflare exempts `/.well-known/acme-challenge/`
   from HTTPS redirects). If issuance fails on first boot, temporarily set the record to
   "DNS only", wait for `make prod-logs` to show the certificate, then re-enable the proxy.
3. Optional second layer: a WAF rate-limiting rule (one is free) on `/v1/execute`, e.g.
   60 requests per minute per IP, and a firewall rule allowing only Cloudflare's IP ranges
   to reach ports 80/443 on the VM so the `CF-Connecting-IP` header cannot be spoofed.

Check:

```sh
curl -s https://api.glimpse.daviskeene.com/health
curl -s https://api.glimpse.daviskeene.com/v1/execute -H 'content-type: application/json' \
  -d '{"language":"rust","code":"fn main(){println!(\"hi\")}"}'
```

### 4. Keep it running

- **Monitor**: a free uptime check (UptimeRobot, Better Stack, …) on `/health`.
- **Refresh toolchains monthly**: `git pull && make prod` (rebuilds the images; `make prod`
  also prunes the old ones). Reboots are safe — leaked sandboxes are swept on start.
- **Look at it occasionally**: `make prod-logs`; every execution logs one line with the
  language, phase, exit code and timing.
- **Point the demo at it**: `demo/.env.production` holds the API URL used by `npm run
  build`; rebuild and redeploy the static site. `GLIMPSE_CORS_ORIGINS` stays `*` so anyone
  can call the API from their own web app — that is the point of a free instance.

What this setup deliberately accepts: containers share the VM's kernel, so a kernel
exploit gets an attacker this throwaway VM and nothing else (see
[security.md](security.md)). If that is not acceptable for you, use the Lambda backend
below.

## 2. AWS Lambda backend

The Lambda image contains the toolchains and `lambda_handler.py`; the API runs anywhere
(a PaaS, a tiny VM) with `GLIMPSE_RUNNER=lambda`.

### Build and push the image

```sh
AWS_REGION=us-east-1
ACCOUNT=$(aws sts get-caller-identity --query Account --output text)
REPO=$ACCOUNT.dkr.ecr.$AWS_REGION.amazonaws.com/glimpse

aws ecr create-repository --repository-name glimpse --region $AWS_REGION 2>/dev/null || true
aws ecr get-login-password --region $AWS_REGION | docker login --username AWS --password-stdin $REPO

docker build --platform linux/amd64 -f lambda/Dockerfile -t glimpse-lambda .
docker tag glimpse-lambda:latest $REPO:latest
docker push $REPO:latest
```

### Create (or update) the function

```sh
# once: an execution role with the basic Lambda logging policy
aws iam create-role --role-name glimpse-lambda \
  --assume-role-policy-document '{"Version":"2012-10-17","Statement":[{"Effect":"Allow","Principal":{"Service":"lambda.amazonaws.com"},"Action":"sts:AssumeRole"}]}'
aws iam attach-role-policy --role-name glimpse-lambda \
  --policy-arn arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole

aws lambda create-function --function-name glimpse --package-type Image \
  --code ImageUri=$REPO:latest \
  --role arn:aws:iam::$ACCOUNT:role/glimpse-lambda \
  --memory-size 2048 --timeout 90 --ephemeral-storage Size=1024 \
  --region $AWS_REGION

# later deploys
aws lambda update-function-code --function-name glimpse --image-uri $REPO:latest --region $AWS_REGION
```

`--timeout 90` leaves room for a 30 s run plus a 60 s Kotlin compile; `--memory-size 2048`
also buys CPU (Lambda scales CPU with memory) which matters for compile times. For a
"no network" guarantee attach the function to a VPC subnet without a NAT gateway.

### Test locally first

The Lambda base image bundles the Runtime Interface Emulator:

```sh
make lambda-build && make lambda-local     # serves on :9000
make lambda-smoke                          # in another shell: every language + a timeout
curl -s -XPOST localhost:9000/2015-03-31/functions/function/invocations \
  -d '{"language":"kotlin","code":"fun main(){println(\"hi\")}"}'
```

### Point the API at it

```sh
GLIMPSE_RUNNER=lambda
GLIMPSE_LAMBDA_FUNCTION_NAME=glimpse
AWS_DEFAULT_REGION=us-east-1
AWS_ACCESS_KEY_ID=...          # an IAM user/role allowed lambda:InvokeFunction on the function
AWS_SECRET_ACCESS_KEY=...
```

The API never retries an invocation (that would run the code twice) and uses a read timeout
of `GLIMPSE_MAX_TIMEOUT_S + 120` seconds.

## 3. API on a PaaS (Render, Fly, Railway, ...)

Use the root `Dockerfile` (or `pip install .` + `glimpse serve`) with the environment above.
The container listens on `GLIMPSE_PORT` (default 8000, `GLIMPSE_HOST=0.0.0.0` is set in the
image). Pair it with the Lambda backend — PaaS containers usually cannot run Docker.

Recommended settings for a public instance:

```
GLIMPSE_RATE_LIMIT=30/minute
GLIMPSE_TRUST_PROXY=true
GLIMPSE_CORS_ORIGINS=https://glimpse.daviskeene.com
```

## The demo front-end

`demo/` is a static Vite build. Set `VITE_GLIMPSE_API_URL` to your API's public URL at build
time (`demo/.env.example`), run `npm run build`, and host `demo/dist/` anywhere static
(GitHub Pages, Netlify, S3). Remember to allow that origin in `GLIMPSE_CORS_ORIGINS`.
