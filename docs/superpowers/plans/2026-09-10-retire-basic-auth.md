# Retire Basic Auth Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Remove the HTTP Basic Auth stopgap (`AURUM_BASIC_AUTH_USER`/
`PASSWORD`, nginx's `auth_basic`, `frontend/docker-entrypoint.d/20-basic-auth.sh`)
now that the frontend has a real per-user JWT login/registration screen
(previous plan, already merged) — the stopgap's own reason for existing
("Aurum has no login system of its own") is no longer true anywhere in the
codebase, and every backend route already enforces real per-user
authentication independently of nginx.

**Architecture:** Pure removal — no new code, no new config knobs. The
`20-basic-auth.sh` entrypoint script and the `openssl`/`.htpasswd`
machinery it drove are deleted outright. `nginx.conf` stops referencing
the config fragment that script used to generate. `docker-compose.yml`
and `.env.example` stop declaring the two env vars. Documentation
(`README.md`, `DOCS.md`) is rewritten to describe the real auth model
(register/login, Bearer tokens, 401 meaning "not authenticated," not
"wrong shared password") instead of the retired one.

**Tech Stack:** Docker, nginx — no application code changes.

**Spec:** none — this is bounded work explicitly named as the next step
in the immediately preceding, already-merged plan
(`docs/superpowers/plans/2026-09-10-frontend-jwt-auth.md`'s own "Next
Plan" section), not a new design decision requiring its own brainstorm.

## Global Constraints

- `GET /api/health` must remain reachable with no auth of any kind
  afterward too (Docker's own `HEALTHCHECK` and external uptime monitors
  depend on this) — it already needs no special handling once Basic Auth
  is gone, since nothing will be setting `auth_basic` anywhere anymore,
  but confirm this explicitly rather than assuming.
- No change to any backend Python file — the backend has never enforced
  Basic Auth itself; it was always purely an nginx-layer, frontend-side
  concern.
- `nginx.conf` must remain valid (the container must actually start) once
  the `include` line pointing at a file nothing generates anymore is
  removed — `nginx -t`-equivalent verification is Step 3 of the one task
  below.

---

## Task 1: Remove Basic Auth end to end

**Files:**
- Delete: `frontend/docker-entrypoint.d/20-basic-auth.sh`
- Modify: `frontend/Dockerfile`
- Modify: `frontend/nginx.conf`
- Modify: `docker-compose.yml`
- Modify: `.env.example`
- Modify: `README.md`
- Modify: `DOCS.md`

**Interfaces:** none — no code interfaces change, this is config/docs only.

- [ ] **Step 1: Delete the entrypoint script**

```bash
git rm frontend/docker-entrypoint.d/20-basic-auth.sh
```

- [ ] **Step 2: Update the Dockerfile**

Modify `frontend/Dockerfile` — replace:

```dockerfile
FROM nginx:1.27-alpine
# openssl generates the htpasswd hash for optional basic auth — see
# docker-entrypoint.d/20-basic-auth.sh.
RUN apk add --no-cache openssl
COPY --from=build /app/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY docker-entrypoint.d/20-basic-auth.sh /docker-entrypoint.d/20-basic-auth.sh
# sed strips any stray CR: cloned on Windows with core.autocrlf=true the
# script arrives as CRLF, the kernel reads the shebang as "/bin/sh\r", and
# nginx dies on boot with "not found" (exit 127). .gitattributes fixes this
# at the repository level; this line covers checkouts that predate it.
RUN sed -i 's/\r$//' /docker-entrypoint.d/20-basic-auth.sh \
    && chmod +x /docker-entrypoint.d/20-basic-auth.sh \
    && touch /etc/nginx/basic-auth.conf

EXPOSE 80
```

with:

```dockerfile
FROM nginx:1.27-alpine
COPY --from=build /app/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf

EXPOSE 80
```

(`openssl` was only ever installed to hash the Basic Auth password;
nothing else in this image needs it. The `docker-entrypoint.d/` script
copy, its CRLF-stripping/chmod step, and the `basic-auth.conf` placeholder
file all existed solely to support that script — all removed together.)

- [ ] **Step 3: Update `nginx.conf`**

Modify `frontend/nginx.conf` — replace the whole file:

```nginx
server {
    listen 80;
    server_name _;
    root /usr/share/nginx/html;
    index index.html;

    # Docker's own HEALTHCHECK and any external uptime monitor hit this —
    # returns nothing but {"status":"ok"}, no auth of any kind, same as
    # every other route here (the app's own JWT login is what actually
    # gates entry — see the /api/ location below).
    location = /api/health {
        proxy_pass http://backend:8000/api/health;
        proxy_set_header Host $host;
    }

    # Reverse proxy to the FastAPI backend container. The backend enforces
    # real per-user authentication itself (JWT access tokens, see
    # backend/app/api/deps.py) — nginx does no auth of its own here.
    location /api/ {
        proxy_pass http://backend:8000/api/;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    }

    # SPA fallback — client-side routing handles the rest. The built
    # HTML/JS/CSS shell itself carries no financial data; the app's own
    # login screen (frontend/src/components/auth/LoginGate.tsx) is what
    # actually gates entry, by requiring a valid Bearer token on every
    # /api/ call above.
    location / {
        try_files $uri $uri/ /index.html;
    }

    gzip on;
    gzip_types text/css application/javascript application/json image/svg+xml;
}
```

- [ ] **Step 4: Update `docker-compose.yml`**

Modify `docker-compose.yml` — replace the `web` service's `environment`
block:

```yaml
    environment:
      # Both unset = no login screen at all. See frontend/docker-entrypoint.d/20-basic-auth.sh.
      AURUM_BASIC_AUTH_USER: ${AURUM_BASIC_AUTH_USER:-}
      AURUM_BASIC_AUTH_PASSWORD: ${AURUM_BASIC_AUTH_PASSWORD:-}
    depends_on:
      - backend
```

with:

```yaml
    depends_on:
      - backend
```

(The whole `environment:` key is removed since it had nothing else in
it — confirm this by reading the current file before editing; if
anything else has been added to this block since this plan was written,
keep that and only remove the two `AURUM_BASIC_AUTH_*` lines plus their
now-inapplicable comment.)

- [ ] **Step 5: Update `.env.example`**

Modify `.env.example` — remove the whole Basic Auth section:

```
# --- Basic auth (STRONGLY recommended if this instance is reachable from
# anywhere other than your own machine) ---
# Aurum has no login system of its own — it's built for one person
# self-hosting their own private instance, not a multi-tenant service.
# Leave both blank and there is NO password on this app at all: anyone who
# can reach it can read, edit, and delete every transaction, account, and
# asset. Set both to put an HTTP Basic Auth prompt in front of the whole
# app (UI + API). See frontend/docker-entrypoint.d/20-basic-auth.sh.
AURUM_BASIC_AUTH_USER=
AURUM_BASIC_AUTH_PASSWORD=

```

(Delete this block entirely, including the trailing blank line before
the next section, so `.env.example` reads directly from the `AURUM_JWT_SECRET`
line into the `# --- Ports exposed on your host machine ---` section with
no orphaned gap.)

- [ ] **Step 6: Update `README.md`**

Modify `README.md` — in the env var table, replace the row:

```
| `AURUM_BASIC_AUTH_USER` / `AURUM_BASIC_AUTH_PASSWORD` | **Aurum has no login screen of its own.** Leave these blank and the app has no password at all — fine if it's only reachable from `localhost`, not fine anywhere else. Set both to put an HTTP Basic Auth prompt in front of the whole app. See [Security & Self-Hosting](#-security--self-hosting) below. |
```

with:

```
| `AURUM_JWT_SECRET` | Signing key for login sessions — generate a real one with `openssl rand -hex 32`. See [Security & Self-Hosting](#-security--self-hosting) below. |
```

(This row didn't exist before for `AURUM_JWT_SECRET` even though the
variable itself already existed in `.env.example` — this plan's own
research found the README's env var table never mentioned it at all.
Adding this row is a small, directly-related documentation gap this
plan is well-positioned to close while already editing this exact table,
not scope creep.)

Then replace the "Security & Self-Hosting" section's Basic-Auth-specific
paragraph:

```
**Aurum has no built-in login system.** It's built for one person to self-host one private instance of their own financial data — not as a multi-tenant service with per-user accounts. That's a deliberate trade-off, not an oversight, but it means:

- If you leave `AURUM_BASIC_AUTH_USER` / `AURUM_BASIC_AUTH_PASSWORD` unset in `.env`, **anyone who can reach the container can read, edit, and delete all of it — no password prompt at all.** This is fine if Aurum is only reachable from `localhost` or your own private network.
- Set both variables before exposing your instance beyond your own machine (a VPS, a subdomain, a Tailscale/VPN endpoint someone else might share). This turns on an HTTP Basic Auth prompt in front of the entire app, UI and API alike.
- For anything beyond that — a reverse proxy with TLS (Caddy, Traefik, nginx + Let's Encrypt) is on you; Aurum doesn't terminate HTTPS itself.
```

with:

```
**Aurum has its own per-user login.** Anyone with access to the app can register their own account (email + password) and only ever sees their own data — accounts, transactions, assets, everything is private to the user who created it. A few things to know:

- Set a real `AURUM_JWT_SECRET` in `.env` before running this anywhere other than your own machine — the placeholder value signs every login session with a key anyone could read straight out of this repo, letting them forge a valid session for any account. The backend refuses to start with the placeholder still set.
- Registration is open by default — anyone who can reach the app can create an account. If you're self-hosting for just yourself or a small trusted group, keep the instance off the public internet (a VPN/Tailscale endpoint, a private network) rather than relying on registration friction to keep strangers out.
- For anything beyond that — a reverse proxy with TLS (Caddy, Traefik, nginx + Let's Encrypt) is on you; Aurum doesn't terminate HTTPS itself.
```

- [ ] **Step 7: Update `DOCS.md`**

Modify `DOCS.md` — replace the "Auth" section:

```
### Auth

Aurum has no built-in login system or API keys — it's designed for one person to self-host one
private instance. Access control is whatever you put in front of it:

- **Nothing set:** if `AURUM_BASIC_AUTH_USER` / `AURUM_BASIC_AUTH_PASSWORD` are empty in `.env`
  (the default), the API is completely open to anyone who can reach the host — no credentials
  needed. Fine for `localhost`-only or a private network; **not** fine on the public internet.
- **HTTP Basic Auth:** set both `AURUM_BASIC_AUTH_USER` and `AURUM_BASIC_AUTH_PASSWORD` in `.env`
  and restart (`docker compose up -d`). Every request — UI and API alike — then requires an
  `Authorization: Basic <base64(user:password)>` header, or the equivalent `-u user:password` flag
  in curl.

```bash
# No auth configured
curl http://localhost:3000/api/accounts

# Basic Auth configured
curl -u myuser:mypassword http://localhost:3000/api/accounts
```

`GET /api/health` is always open (no auth), even with Basic Auth configured — it exists for Docker
healthchecks and uptime monitors.

There's no per-endpoint permission model beyond this: whoever can authenticate can read, create,
update, and delete everything.
```

with:

```
### Auth

Aurum uses real per-user accounts — every request (except `GET /api/health`) requires a valid JWT
access token, obtained by registering or logging in:

```bash
# Register a new account
curl -X POST http://localhost:3000/api/auth/register \
  -H "Content-Type: application/json" \
  -d '{"email": "you@example.com", "password": "a-real-password"}'
# -> {"access_token": "...", "refresh_token": "...", "token_type": "bearer"}

# Use the access token on every subsequent request
curl http://localhost:3000/api/accounts \
  -H "Authorization: Bearer <access_token>"
```

Access tokens expire after 15 minutes — exchange the refresh token (valid 30 days) for a fresh
pair via `POST /api/auth/refresh` with `{"refresh_token": "..."}` rather than logging in again.
`POST /api/auth/logout` (same body shape) revokes a refresh token immediately.

`GET /api/health` is always open (no auth) — it exists for Docker healthchecks and uptime monitors.

There's no per-endpoint permission model beyond "is this your own data": every account, transaction,
asset, and setting is private to the user who created it — whoever authenticates as a given user can
read, create, update, and delete only that user's own data, never anyone else's.
```

Then fix the status-code table's `401` row:

```
| `401` | Missing/invalid Basic Auth credentials (only when Basic Auth is configured) |
```

replace with:

```
| `401` | Missing, invalid, or expired access token |
```

- [ ] **Step 8: Verify the container actually builds and starts cleanly**

From the repo root:

```bash
docker compose build web
docker compose up -d
docker compose logs web --tail 20
```

Expected: the build succeeds (no `apk add`/COPY errors for the removed
script), the `web` container starts and reports healthy (`docker compose
ps` shows `web` as `healthy`), and `curl -sf http://localhost:${AURUM_WEB_PORT:-3000}/api/health`
returns `{"status":"ok"}` with no credentials of any kind. Then confirm
the app itself still works: `curl -s http://localhost:${AURUM_WEB_PORT:-3000}/api/accounts`
(no `Authorization` header at all) should now return a `401` from the
BACKEND's own JWT check (not an nginx-level Basic Auth 401 — there's no
way to tell these apart by status code alone, but confirm the response
body is FastAPI's own `{"detail": "Not authenticated"}` shape, not an
nginx-generated HTML 401 page, proving nginx is no longer the one
rejecting the request).

- [ ] **Step 9: Run the backend test suite as a regression check**

Run: `docker compose exec backend pytest -q`
Expected: unchanged from before this plan (this plan touches no backend
code) — the same passing count as whatever the suite currently reports.
This step exists only to catch an unrelated regression from the `docker
compose build`/`up` cycle in Step 8, not because this plan's own changes
could plausibly affect backend tests.

- [ ] **Step 10: Commit**

```bash
git add frontend/Dockerfile frontend/nginx.conf docker-compose.yml .env.example README.md DOCS.md
git commit -m "Отключить Basic Auth — теперь есть настоящий вход на JWT"
```

---

## Plan Self-Review Notes

- **Spec coverage:** implements the "Next Plan" step explicitly named at
  the end of the immediately preceding, already-merged plan
  (`2026-09-10-frontend-jwt-auth.md`).
- **Placeholder scan:** every step contains complete, real before/after
  text for every file — no elided sections.
- **Consistency check:** confirmed via direct reading of the current
  repo state (not memory) that `frontend/nginx.conf`'s `/api/health`
  location, the `include /etc/nginx/basic-auth.conf` line, and
  `docker-compose.yml`'s exact `environment:` block all match this plan's
  "before" text verbatim before finalizing the "after" text.

---

## Next Plan

**Android app (Capacitor wrapper):** the originally-requested feature this
entire multi-tenant conversion was undertaken to unblock. With real
per-user accounts, a real login screen, and no more shared-password
stopgap, the app is now in a state where a mobile wrapper makes sense —
each installed copy of the app can be its own user's own private session
against a shared, multi-tenant backend.
