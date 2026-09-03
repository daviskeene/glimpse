# deploy/

Files for running a public Glimpse instance on one VM. The recipe is in
[docs/deploy.md](../docs/deploy.md).

- `docker-compose.prod.yml` — overlay on the root `docker-compose.yml`: adds Caddy (TLS) in
  front of the loopback-only API, turns on proxy-aware + global rate limiting, rotates logs.
- `Caddyfile` — reverse proxy for `$GLIMPSE_DOMAIN` with automatic certificates.

```sh
make prod          # docker compose -f docker-compose.yml -f deploy/docker-compose.prod.yml up -d --build
make prod-logs     # follow api + caddy logs
```
