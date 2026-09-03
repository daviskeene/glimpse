# syntax=docker/dockerfile:1
# Glimpse Lambda image. Build from the repository root:
#   docker build -f lambda/Dockerfile -t glimpse-lambda .
# The function runs `glimpse.execution.execute_local` inside the Lambda micro-VM;
# see docs/deploy.md for pushing to ECR and creating the function.

FROM --platform=linux/amd64 public.ecr.aws/lambda/python:3.12

ARG GO_VERSION=1.25.3
ARG NODE_VERSION=22.20.0
ARG KOTLIN_VERSION=2.2.20
ARG RUST_VERSION=1.91.0

RUN dnf install -y gcc gcc-c++ make tar gzip xz unzip java-17-amazon-corretto-devel \
 && dnf clean all

# --- Node.js ------------------------------------------------------------------
RUN set -eux; \
    curl -fsSL "https://nodejs.org/dist/v${NODE_VERSION}/node-v${NODE_VERSION}-linux-x64.tar.xz" \
      -o /tmp/node.tar.xz; \
    tar -xJf /tmp/node.tar.xz -C /usr/local --strip-components=1 \
      --exclude='*/share' --exclude='*/include' --exclude='*/lib/node_modules' \
      --exclude='*/bin/npm' --exclude='*/bin/npx' --exclude='*/bin/corepack'; \
    rm /tmp/node.tar.xz; \
    node --version

# --- Go -----------------------------------------------------------------------
RUN set -eux; \
    curl -fsSL "https://go.dev/dl/go${GO_VERSION}.linux-amd64.tar.gz" | tar -xz -C /usr/local; \
    /usr/local/go/bin/go version

# --- Kotlin -------------------------------------------------------------------
RUN set -eux; \
    curl -fsSL "https://github.com/JetBrains/kotlin/releases/download/v${KOTLIN_VERSION}/kotlin-compiler-${KOTLIN_VERSION}.zip" \
      -o /tmp/kotlin.zip; \
    unzip -q /tmp/kotlin.zip -d /opt; \
    rm /tmp/kotlin.zip

# --- Rust ---------------------------------------------------------------------
ENV RUSTUP_HOME=/opt/rustup \
    CARGO_HOME=/opt/cargo
RUN set -eux; \
    curl -fsSL "https://static.rust-lang.org/rustup/dist/x86_64-unknown-linux-gnu/rustup-init" \
      -o /tmp/rustup-init; \
    chmod +x /tmp/rustup-init; \
    /tmp/rustup-init -y --profile minimal --default-toolchain "${RUST_VERSION}" --no-modify-path; \
    rm /tmp/rustup-init; \
    ln -s "/opt/rustup/toolchains/${RUST_VERSION}-x86_64-unknown-linux-gnu" /opt/rust; \
    chmod -R a+rX /opt/rustup /opt/cargo

ENV PATH="/opt/rust/bin:/usr/local/go/bin:/opt/kotlinc/bin:${PATH}" \
    LANG=C.UTF-8 \
    LC_ALL=C.UTF-8

RUN kotlinc -version && rustc --version

# --- Python libraries available to user code ---------------------------------
COPY sandbox/requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt && rm /tmp/requirements.txt

# --- Pre-warm the Go build cache (the Lambda filesystem is read-only except /tmp)
ENV GOCACHE=/opt/gocache
RUN set -eux; \
    mkdir -p /opt/gocache; \
    HOME=/tmp GOPATH=/tmp/go go build \
      fmt os io bufio bytes strings strconv sort math math/rand math/big math/bits \
      errors time sync sync/atomic slices maps unicode unicode/utf8 regexp \
      encoding/json encoding/binary encoding/hex encoding/base64 encoding/csv \
      container/heap container/list container/ring context text/template text/tabwriter \
      crypto/sha256 crypto/md5 crypto/sha1 hash/fnv hash/crc32 runtime/debug \
      iter cmp; \
    chmod -R a+rX /opt/gocache

# Go "trims" its cache once a day and aborts the build if it cannot rewrite
# GOCACHE/trim.txt -- fatal on a read-only cache 24 h after the image was built. Point
# the file at the writable scratch dir instead; the trim itself is a no-op on a
# read-only tree (removals fail silently) and the cache hits keep working.
RUN rm -f /opt/gocache/trim.txt && ln -s /tmp/glimpse-gocache-trim.txt /opt/gocache/trim.txt

# --- Function code (stdlib only: no third-party packages needed) --------------
COPY glimpse ${LAMBDA_TASK_ROOT}/glimpse
COPY lambda_handler.py ${LAMBDA_TASK_ROOT}/

CMD ["lambda_handler.handler"]
