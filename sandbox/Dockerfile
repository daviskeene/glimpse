# syntax=docker/dockerfile:1
#
# Glimpse sandbox image.
#
# This image contains ONLY the language toolchains that user code needs. It never
# contains application code, configuration or secrets, and it is never run with
# network access. Every execution gets a fresh container from this image which is
# destroyed afterwards. See docs/security.md.

FROM python:3.12-slim-bookworm

ARG TARGETARCH
ARG GO_VERSION=1.25.3
ARG NODE_VERSION=22.20.0
ARG KOTLIN_VERSION=2.2.20
ARG RUST_VERSION=1.91.0

ENV DEBIAN_FRONTEND=noninteractive \
    LANG=C.UTF-8 \
    LC_ALL=C.UTF-8

RUN apt-get update \
 && apt-get install -y --no-install-recommends \
      ca-certificates curl xz-utils unzip \
      gcc g++ libc6-dev make \
      openjdk-17-jdk-headless \
 && rm -rf /var/lib/apt/lists/*

# --- Node.js (runtime only; npm/npx/corepack are stripped) ---------------------
RUN set -eux; \
    case "${TARGETARCH}" in \
      amd64) NODE_ARCH=x64 ;; \
      arm64) NODE_ARCH=arm64 ;; \
      *) echo "unsupported TARGETARCH=${TARGETARCH}" >&2; exit 1 ;; \
    esac; \
    curl -fsSL "https://nodejs.org/dist/v${NODE_VERSION}/node-v${NODE_VERSION}-linux-${NODE_ARCH}.tar.xz" \
      -o /tmp/node.tar.xz; \
    tar -xJf /tmp/node.tar.xz -C /usr/local --strip-components=1 \
      --exclude='*/share' --exclude='*/include' --exclude='*/lib/node_modules' \
      --exclude='*/bin/npm' --exclude='*/bin/npx' --exclude='*/bin/corepack'; \
    rm /tmp/node.tar.xz; \
    node --version

# --- Go -------------------------------------------------------------------------
RUN set -eux; \
    curl -fsSL "https://go.dev/dl/go${GO_VERSION}.linux-${TARGETARCH}.tar.gz" | tar -xz -C /usr/local; \
    /usr/local/go/bin/go version
ENV PATH="/usr/local/go/bin:${PATH}"

# --- glimpse-run: the in-sandbox supervisor (see glimpse-run/main.go) -----------
COPY glimpse-run /tmp/glimpse-run
RUN set -eux; \
    cd /tmp/glimpse-run; \
    CGO_ENABLED=0 GOCACHE=/tmp/gocache-build GOFLAGS=-mod=mod go build -trimpath \
      -ldflags='-s -w' -o /usr/local/bin/glimpse-run .; \
    rm -rf /tmp/glimpse-run /tmp/gocache-build; \
    /usr/local/bin/glimpse-run -t 5 -- true

# --- Rust (rustup, minimal profile; the real toolchain dir goes on PATH) --------
ENV RUSTUP_HOME=/opt/rustup \
    CARGO_HOME=/opt/cargo
RUN set -eux; \
    case "${TARGETARCH}" in \
      amd64) RUST_ARCH=x86_64 ;; \
      arm64) RUST_ARCH=aarch64 ;; \
      *) echo "unsupported TARGETARCH=${TARGETARCH}" >&2; exit 1 ;; \
    esac; \
    curl -fsSL "https://static.rust-lang.org/rustup/dist/${RUST_ARCH}-unknown-linux-gnu/rustup-init" \
      -o /tmp/rustup-init; \
    chmod +x /tmp/rustup-init; \
    /tmp/rustup-init -y --profile minimal --default-toolchain "${RUST_VERSION}" --no-modify-path; \
    rm /tmp/rustup-init; \
    ln -s "/opt/rustup/toolchains/${RUST_VERSION}-${RUST_ARCH}-unknown-linux-gnu" /opt/rust; \
    chmod -R a+rX /opt/rustup /opt/cargo; \
    /opt/rust/bin/rustc --version
ENV PATH="/opt/rust/bin:${PATH}"

# --- Kotlin ---------------------------------------------------------------------
RUN set -eux; \
    curl -fsSL "https://github.com/JetBrains/kotlin/releases/download/v${KOTLIN_VERSION}/kotlin-compiler-${KOTLIN_VERSION}.zip" \
      -o /tmp/kotlin.zip; \
    unzip -q /tmp/kotlin.zip -d /opt; \
    rm /tmp/kotlin.zip; \
    /opt/kotlinc/bin/kotlinc -version
ENV PATH="/opt/kotlinc/bin:${PATH}"

# --- Python libraries available to user code -----------------------------------
COPY requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt && rm /tmp/requirements.txt

# --- Pre-warm the Go build cache -------------------------------------------------
# Go >= 1.20 compiles the standard library on demand into GOCACHE. The rootfs is
# read-only at run time, so we warm a cache for the commonly used packages here;
# Go only needs read access for cache hits and puts the user's own package in /tmp.
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

# --- Unprivileged user + scratch dirs ---------------------------------------------
# /work and /tmp are replaced by size-capped tmpfs mounts at run time; the
# directories just need to exist in the image so they can be mounted over.
RUN useradd --uid 1000 --user-group --create-home --shell /usr/sbin/nologin sandbox \
 && mkdir -p /work \
 && chown sandbox:sandbox /work \
 && chmod 1777 /tmp

USER sandbox
WORKDIR /work
ENV HOME=/work

# Keep-alive process; the runner exec()s user code into the container.
CMD ["sleep", "infinity"]
