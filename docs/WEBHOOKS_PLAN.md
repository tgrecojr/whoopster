# Whoop Webhooks — Implementation Plan

> ## ⛔ DEFERRED — not being implemented
>
> Webhooks are **completely deferred**. The two data-correctness gaps that
> motivated them (§1: silent deletions and missed late rescores) are now closed
> by a **windowed reconciliation poll** instead — no inbound endpoint, no
> FastAPI/uvicorn receiver, and no Cloudflare WAF cost. See
> `src/services/reconcile.py` and the recovery/cycle upsert + dedup migration.
>
> The rest of this document is **retained for reference only**, in case real-time
> webhooks are ever revisited (e.g. to relax the poll cadence). If picked back up,
> it should be built on Cloudflare's free tier (in-app method/path + rate limiting,
> free edge DDoS), not the $20/mo Pro plan.
>
> _Original status: proposed / under review (receiver in-process with the
> scheduler; 15-minute poll kept as a reconciliation backup)._

## 1. Why we're doing this (the actual motivation)

Timeliness is **not** the driver — 15-minute polling is fresh enough. The real
gaps are data-correctness problems that polling cannot structurally fix:

1. **Deletions are silently dropped, permanently.** Every service uses
   `INSERT ... ON CONFLICT DO UPDATE` (e.g. `src/services/sleep_service.py:168`).
   There is no code path that ever deletes a row. If a record is deleted in the
   Whoop app (mis-detected nap, rescore, bad record), the stale row lives in
   Postgres forever. Polling list endpoints can't observe "this used to exist."
   Only the `*.deleted` webhook events surface this.

2. **Late rescoring of older records can be missed.** Incremental sync sets the
   watermark to `last_record_time = max(record.end)`
   (`src/services/sleep_service.py:190-198`) and queries `start = last_record_time`
   next time. Whoop's `start`/`end` params filter on the record's *time range*,
   not its *updated* time. Once the watermark passes a record's end, a later
   rescore of that same record (`PENDING_SCORE → SCORED`, recovery finalizing
   hours later, a manually edited sleep) won't be re-fetched. `*.updated` events
   catch exactly this.

3. **~96 polls/day that mostly return nothing** — minor here, but webhooks
   remove the wasted API calls and rate-limit pressure.

## 2. The constraint that shapes everything: webhooks are partial

Whoop only emits webhooks for **sleep, recovery, and workout**. The docs
explicitly state there are **no webhooks for Day Strain, cycles, or body
measurements**. We sync all five (`src/services/data_collector.py:106`).

Therefore this is **hybrid, not a replacement**:

- **Webhooks** drive sleep / recovery / workout (including deletes).
- **Polling stays** for cycles + body measurements (no other option).
- **Polling also stays as a backup** for the webhook-covered types — Whoop's own
  docs warn webhooks can be missed and recommend "a reconciliation job that can
  occasionally reach out to the WHOOP API." Per decision, we keep the existing
  15-minute cadence as that safety net (can be relaxed later).

## 3. Whoop webhook spec (reference)

Source: <https://developer.whoop.com/docs/developing/webhooks/>

**Event types (6):**
`recovery.updated`, `recovery.deleted`, `workout.updated`, `workout.deleted`,
`sleep.updated`, `sleep.deleted`.

**Payload (POST body):**
```json
{
  "user_id": 10129,
  "id": 10235,
  "type": "workout.updated",
  "trace_id": "d3709ee7-104e-4f70-a928-2932964b017b"
}
```
- `user_id` (int64) — the **Whoop** user id (not our internal `users.id`).
- `id` — resource id; **v2 = UUID** (v1 = integer). We use v2 endpoints.
- `type` — one of the 6 enums above.
- `trace_id` — use for deduplication; duplicate deliveries are possible.

**Signature headers:**
- `X-WHOOP-Signature` — base64 signature value.
- `X-WHOOP-Signature-Timestamp` — milliseconds since epoch.

**Verification:**
```
calculated = base64( HMAC_SHA256( timestamp_header + raw_request_body, client_secret ) )
```
Compare `calculated` to `X-WHOOP-Signature` (constant-time). The client secret is
the Whoop app's secret (we already hold it as `WHOOP_CLIENT_SECRET`).

**Response/retry:**
- Must return a `2XX` **within ~1 second**. Anything else (or a timeout) counts
  as failure.
- Whoop retries failed deliveries **5 times over ~1 hour**.
- Webhooks are notifications only — the body carries no data; we must call the
  API by `id` to fetch the actual record.
- Deliveries may be missed entirely → reconciliation poll is mandatory.

## 4. Application changes

### 4.1 Dependencies (`pyproject.toml`)
- `fastapi`, `uvicorn[standard]` — pinned `==` per project convention.

### 4.2 Config (`src/config.py`)
- `webhook_enabled: bool = False` — ships **dark**; flip on after Cloudflare + Whoop registration.
- `webhook_port: int = 8080`
- `webhook_path: str = "/webhooks/whoop"`
- `webhook_signature_max_age_seconds: int = 300` — replay window.
- Reuse existing `whoop_client_secret` for HMAC.

### 4.3 New package `src/webhooks/`
- **`signature.py`** — `verify(timestamp_header, raw_body, signature_header) -> bool`:
  compute `base64(HMAC_SHA256(timestamp + raw_body, client_secret))`,
  constant-time compare, reject stale timestamps (> max age).
- **`app.py`** — FastAPI app with one `POST {webhook_path}` route plus `GET /healthz`:
  1. Read the **raw** body bytes (hash the exact bytes — before JSON parsing).
  2. Verify signature → `401` on failure.
  3. Parse `{user_id, id, type, trace_id}`.
  4. Dedup on `trace_id` (see 4.6).
  5. **Enqueue** onto an in-process `asyncio.Queue`, return `200` immediately
     (stays well under Whoop's ~1s timeout).
- **`worker.py`** — async consumer draining the queue:
  - `*.updated` → fetch the single resource by id → existing transform + upsert.
  - `*.deleted` → delete the row. **Open decision:** hard delete (mirror Whoop)
    vs. soft delete with a `deleted_at` tombstone for our own history.
  - Resolve Whoop `user_id` → internal `users.id`.

### 4.4 Whoop client (`src/api/whoop_client.py`)
Add single-resource fetchers (reuse `_make_request`):
- `get_sleep_by_id(id)`     → `GET /developer/v2/activity/sleep/{id}`
- `get_workout_by_id(id)`   → `GET /developer/v2/activity/workout/{id}`
- `get_recovery_by_id(id)`  → `GET /developer/v2/recovery/{id}` *(confirm exact path)*

### 4.5 Lifecycle wiring (`src/main.py`)
- In `startup()`, when `webhook_enabled`, launch uvicorn as an asyncio task on the
  same loop as APScheduler; cancel it in `shutdown()`. The scheduler is unchanged
  (15-min poll = backup + the only path for cycles/body measurement).

### 4.6 Migration (Alembic)
- New `webhook_events` table for `trace_id` dedup + audit:
  `trace_id` (PK/unique), `event_type`, `whoop_user_id`, `resource_id`,
  `received_at`, `processed_at`, `status`. DB-backed dedup survives restarts
  (preferred over in-memory).

### 4.7 Mapping prerequisite
- The receiver needs `users.whoop_user_id` populated to resolve the internal id.
  Confirm the column exists/is populated; add a one-time backfill if not.

### 4.8 Tests (`tests/`)
- Signature: valid / tampered body / stale timestamp / wrong secret.
- Routing: `updated` → fetch + upsert; `deleted` → row removed; unknown user;
  duplicate `trace_id` ignored.
- Returns `200` before processing (enqueue, not inline).

## 5. Cloudflare design — **review this carefully**

### 5.1 The critical gotcha
Our existing `cloudflared` runs **Zero Trust Access** (auth in front of services).
We **cannot** put the webhook behind an Access policy: Whoop is an unauthenticated
third party and would be bounced to a login page, so every delivery would fail.

The webhook hostname must be **publicly reachable with no Access policy**, and
protected by other layers instead.

### 5.2 Topology
```
Whoop  ──HTTPS POST──▶  Cloudflare edge (WAF + rate limit + DDoS)
                              │
                              ▼
                     cloudflared tunnel (existing container)
                              │  public hostname, NO Access policy
                              ▼
                     app container :8080  /webhooks/whoop
                              │
                              ▼
                     HMAC verify → enqueue → 200
```

### 5.3 Tunnel config — add a public hostname
Add an ingress rule to the existing tunnel (example `config.yml`; adapt to however
your cloudflared is currently configured — dashboard-managed tunnels do the
equivalent under Public Hostnames):

```yaml
ingress:
  # NEW: Whoop webhook receiver — public, NOT behind Access
  - hostname: whoop-hooks.example.com
    service: http://app:8080
    # no "access" / no Zero Trust application bound to this hostname

  # ... existing Zero-Trust-protected hostnames stay as they are ...

  - service: http_status:404
```

> If the tunnel is **dashboard-managed**: add a Public Hostname
> `whoop-hooks.example.com → http://app:8080` and make sure **no Access
> application** is configured to match that hostname/path.

### 5.4 WAF / security layers (the real protection)
Because there's no Access gate, security comes from:

1. **HMAC signature verification in-app** — the actual authentication. Only Whoop
   knows our client secret. This is non-negotiable and is the primary control.
2. **WAF custom rule** — only allow the exact method + path, block the rest, e.g.:
   ```
   (http.host eq "whoop-hooks.example.com"
     and not (http.request.method eq "POST"
              and http.request.uri.path eq "/webhooks/whoop"))
   ```
   → action: **Block**.
3. **Rate limiting rule** on the hostname (e.g. N requests / 10s per IP) — Whoop's
   real volume is tiny, so a low ceiling is safe.
4. **Managed DDoS protection** — automatic at the Cloudflare edge.
5. Whoop publishes **no source-IP allowlist**, so do **not** rely on IP filtering.
6. Keep the path non-obvious if desired; return generic responses (no detail leak).

### 5.5 Register with Whoop
In the Whoop Developer Dashboard → app settings → **Webhooks**:
- URL: `https://whoop-hooks.example.com/webhooks/whoop`
- **Model Version: v2** (our client uses the v2 UUID endpoints).

## 6. Docker / deploy
- `docker-compose.yml`: the `app` service exposes `8080` **on the Docker network
  only** (cloudflared reaches it as `http://app:8080`; no host port publish needed).
- Add a webhook healthcheck (`GET /healthz`).
- Ansible / secrets deploy mirrors the new env vars (`WEBHOOK_ENABLED`, etc.).

## 7. Rollout order
1. Ship code behind `webhook_enabled=false`; deploy.
2. Add the Cloudflare public hostname + WAF + rate-limit rules.
3. Register the URL in the Whoop Developer Dashboard (v2).
4. Flip `webhook_enabled=true`; watch logs.
5. Verify end-to-end: edit/delete a sleep in the Whoop app → confirm it
   propagates (update applied / row removed).
6. (Later, optional) relax the poll cadence from 15 min toward hourly/daily once
   confident in webhook reliability.

## 8. Open decisions
- **Hard vs soft delete** on `*.deleted` events.
- Confirm `read:*` scopes already cover the by-id endpoints (should match the
  list-endpoint scopes).
- Final public hostname name (`whoop-hooks.<domain>`).
