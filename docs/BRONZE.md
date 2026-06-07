# Bronze Layer (Raw Capture)

The bronze layer preserves the **exact bytes** received from each data source,
once and immutably, so raw data can be reprocessed later without re-fetching
from rate-limited or non-replayable sources (Whoop today; Garmin/CGM/soil
later).

Bronze is a **best-effort side-effect** added alongside existing processing. It
never changes how data is parsed, transformed, or served, and a failed bronze
write never breaks or blocks normal processing.

## Enabling

Bronze is **off by default**. Set `BRONZE_ROOT` to a writable directory to turn
it on:

```bash
BRONZE_ROOT=/data/bronze
```

When `BRONZE_ROOT` is unset or empty, capture is a silent no-op. Nothing else is
hardcoded — repointing `BRONZE_ROOT` (or swapping in an S3 client later) is the
only change needed to move where bronze lives.

## What gets captured

For Whoop, each data response is captured per page, before processing:

| Collection        | Endpoint                                | Notes                          |
| ----------------- | --------------------------------------- | ------------------------------ |
| `recovery`        | `/developer/v2/recovery`                | paginated                      |
| `sleep`           | `/developer/v2/activity/sleep`          | paginated                      |
| `workout`         | `/developer/v2/activity/workout`        | paginated                      |
| `cycle`           | `/developer/v2/cycle`                   | paginated                      |
| `profile`         | `/developer/v2/user/profile/basic`      | single object (reference data) |
| `body_measurement`| `/developer/v2/user/measurement/body`   | single object (reference data) |

Rules applied automatically:

- **OAuth/token responses are never captured** (hard security rule — they carry
  access/refresh tokens). The OAuth client is intentionally not wired to bronze.
- **Error responses with a meaningful body are captured** as diagnostic records
  with their real HTTP status (e.g. a `429` or a `401` missing-scope body), so a
  future gap in the data is explainable. Empty error bodies are skipped.
- **Empty pagination terminators** (the "no more results" page carrying zero
  records) are skipped — no functional value to reprocess.

## Layout

```
{BRONZE_ROOT}/{source}/{collection}/dt={YYYY-MM-DD}/{collection}_{fetched_at_unix_ms}_{short_id}.{ext}
```

`dt=` is partitioned by **fetch date (UTC)**, not event date. Filenames are
never reused; every capture — including re-scores of historical records — is a
new file. Example:

```
whoop/recovery/dt=2026-06-04/recovery_1717459200000_a3f9c1.json
whoop/recovery/dt=2026-06-04/recovery_1717459200000_a3f9c1.meta.json
```

## Sidecar metadata (`.meta.json`)

Each payload is written with a sidecar carrying provenance the raw bytes don't:

```json
{
  "source": "whoop",
  "collection": "recovery",
  "fetched_at": "2026-06-04T08:00:00.000Z",
  "fetched_at_unix_ms": 1717459200000,
  "request_url": "https://api.prod.whoop.com/developer/v2/recovery?limit=25",
  "request_params": { "limit": "25" },
  "http_status": 200,
  "content_type": "application/json",
  "charset": "utf-8",
  "content_encoding": "identity",
  "stored_encoding": "identity",
  "byte_size": 18423,
  "sha256": "e3b0c44298fc1c149afbf4c8996fb924...",
  "processor": "whoop-ingest",
  "processor_version": "1.0.0",
  "schema_version": "v1"
}
```

- **No secrets.** Whoop auth rides in request headers, never the URL or params,
  so `request_url`/`request_params` are safe to record.
- `content_encoding` is the **arrival** encoding over the wire; `stored_encoding`
  is how the bytes sit **on disk**. httpx transparently decompresses transport
  compression, so for Whoop the stored form is always `identity` JSON (`ext`
  reflects the stored form). At-rest compression is not applied in v1.
- `sha256`/`byte_size` are over the **stored** bytes, so integrity is verifiable.

## Storage notes

- Writes are **atomic**: payload and sidecar are each written to a temp file and
  `os.replace`d into place, so a half-written file never appears under the final
  name (maps cleanly to S3 put-once later).
- Bronze is **append-only and immutable** — nothing is ever overwritten,
  deleted, or compacted here. Retention/cleanup is a later concern.

## Backfilling gaps

To "true up" missing bronze data between two dates, run the bronze backfill
**inside the already-running container** (so it inherits the env vars and bronze
volume mount):

```bash
docker exec <container> python -m scripts.backfill_data --start 2025-12-17
docker exec <container> python -m scripts.backfill_data --start 2025-12-17 --end 2026-01-15
docker exec <container> python -m scripts.backfill_data --days 30 --types sleep recovery
```

It fetches the range from the Whoop API so each raw page is captured to bronze;
**nothing is written to the database**. Only range-based collections can be
backfilled (`sleep`, `recovery`, `workout`, `cycle`); `profile` and
`body_measurement` are current-snapshot endpoints with no date range. If
`BRONZE_ROOT` is unset the command exits with an error (there would be nothing
to write).

### Staying under the API rate limit

The poller and a backfill run as **separate processes** in the same container,
each with its own in-memory rate limiter — so they must never call the Whoop API
at the same time. They are serialized by an advisory file lock
(`src/utils/sync_lock.py`) at `SYNC_LOCK_PATH` (default `/tmp/whoop_sync.lock`):

- the backfill takes the lock (waiting up to `SYNC_LOCK_TIMEOUT_SECONDS` for any
  in-flight poll to finish), then holds it for the whole run;
- the poller takes the lock non-blocking and **skips that cycle** if a backfill
  holds it, catching up on the next interval.

Because only one process ever hits the API at a time, the per-process limiter is
enough to stay under the limit. The lock is released automatically by the kernel
if a process exits or crashes, so there is no stale lock to clean up.

## Implementation

- `src/bronze/capture.py` — the writer (`capture_bronze`, atomic writes,
  sidecar, naming). Self-contained and source-agnostic.
- `src/api/whoop_client.py` — captures at the single request chokepoint
  (`_make_request`), threading a `collection` label from each fetch method.
- `scripts/backfill_data.py` — bronze-only, lock-serialized range backfill.
- `src/utils/sync_lock.py` — the advisory file lock that serializes the poller
  and backfill.
