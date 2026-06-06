"""Write raw source bytes to the bronze layer.

This module implements the bronze write procedure: it takes the exact bytes a
processor received from a source, derives the standard path/key, and writes the
payload plus a ``.meta.json`` sidecar atomically (temp file + rename).

Design constraints (from the bronze spec):

* **Bytes only.** Payloads are written byte-for-byte from ``response.content``;
  never from a decoded string. Decoding is left to a downstream (silver) layer
  where it is reversible.
* **Append-only / immutable.** Every capture is a new, uniquely named file.
  Nothing is ever overwritten or deleted here.
* **Non-fatal.** :func:`capture_bronze` never raises; any failure is logged as a
  warning and swallowed so the caller's normal processing continues.
* **Swappable root.** The bronze root comes solely from ``BRONZE_ROOT`` (via
  settings); nothing is hardcoded, keeping the S3 migration path open.

For v1 the stored bytes are written as-received from the HTTP client (which has
already transparently decompressed any transport ``Content-Encoding``), so
``stored_encoding`` is ``identity`` and no at-rest compression is applied.
"""

import hashlib
import json
import os
import secrets
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from src.config import settings
from src.utils.logging_config import get_logger

logger = get_logger(__name__)

# Bumped if the sidecar shape changes in a backward-incompatible way.
SCHEMA_VERSION = "v1"

# Map a media type + on-disk encoding to the file extension that reflects the
# *stored* form (not the arrival form). Kept deliberately small; unknown types
# fall back to ``bin`` so we never guess wrong about structure.
_CONTENT_TYPE_EXT = {
    "application/json": "json",
    "text/json": "json",
    "text/csv": "csv",
    "application/csv": "csv",
    "application/xml": "xml",
    "text/xml": "xml",
    "text/plain": "txt",
}


def is_bronze_enabled() -> bool:
    """Return True when a bronze root is configured.

    When ``BRONZE_ROOT`` is unset/empty, bronze capture is a silent no-op so
    existing deployments and tests are unaffected until capture is opted into.
    """
    return bool(settings.bronze_root)


def _ext_for(content_type: Optional[str], stored_encoding: str) -> str:
    """Pick the file extension for the *stored* bytes.

    ``content_type`` selects the base extension; ``stored_encoding`` appends a
    compression suffix only when the bytes are actually compressed on disk.
    """
    base = _CONTENT_TYPE_EXT.get((content_type or "").split(";")[0].strip().lower(), "bin")
    if stored_encoding and stored_encoding.lower() == "gzip":
        return f"{base}.gz"
    return base


def _utc_now_ms() -> int:
    """Current UTC time as Unix epoch milliseconds."""
    return int(datetime.now(timezone.utc).timestamp() * 1000)


def _write_atomic(path: str, data: bytes) -> None:
    """Write ``data`` to ``path`` atomically via a temp file + rename.

    A half-written file never appears under the final name. ``os.replace`` is
    atomic on a local filesystem and maps cleanly to S3 put-once semantics
    later. The temp file lives in the same directory so the rename stays on one
    filesystem.
    """
    directory = os.path.dirname(path)
    os.makedirs(directory, exist_ok=True)
    # Unique temp name avoids collisions between concurrent captures.
    tmp_path = os.path.join(directory, f".tmp_{secrets.token_hex(8)}")
    try:
        with open(tmp_path, "wb") as fh:
            fh.write(data)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp_path, path)
    except Exception:
        # Best-effort cleanup; never mask the original error.
        try:
            os.remove(tmp_path)
        except OSError:
            pass
        raise


def capture_bronze(
    source: str,
    collection: str,
    raw_bytes: bytes,
    meta: Dict[str, Any],
) -> Optional[str]:
    """Write raw source bytes (and a sidecar) to the bronze layer.

    Best-effort and non-fatal: on any failure this logs a warning and returns
    ``None`` rather than raising, so the caller's normal processing continues.

    Args:
        source: Data provider, lowercase (e.g. ``"whoop"``).
        collection: Dataset within the source, lowercase (e.g. ``"recovery"``).
        raw_bytes: The exact response body as **bytes** (never a decoded
            string). The whole value of bronze is that these are untouched.
        meta: Provenance fields for the sidecar. ``sha256``, ``byte_size``,
            ``fetched_at``, ``fetched_at_unix_ms``, ``source``, ``collection``,
            and ``schema_version`` are filled in here; anything else (e.g.
            ``request_url``, ``request_params``, ``http_status``,
            ``content_type``, ``charset``, ``content_encoding``,
            ``stored_encoding``, ``processor``, ``processor_version``) is passed
            through as supplied. **Must not** contain secrets.

    Returns:
        The payload path written, or ``None`` if capture was skipped or failed.
    """
    try:
        if not is_bronze_enabled():
            return None

        if not isinstance(raw_bytes, (bytes, bytearray)):
            # Guard the core invariant: bronze stores bytes, not decoded text.
            raise TypeError(
                f"raw_bytes must be bytes, got {type(raw_bytes).__name__}"
            )

        bronze_root = settings.bronze_root
        fetched_ms = _utc_now_ms()
        fetched_dt = datetime.fromtimestamp(fetched_ms / 1000, tz=timezone.utc)
        dt = fetched_dt.strftime("%Y-%m-%d")
        short_id = secrets.token_hex(3)  # 6 hex chars

        stored_encoding = meta.get("stored_encoding", "identity")
        ext = _ext_for(meta.get("content_type"), stored_encoding)

        rel_base = f"{source}/{collection}/dt={dt}/{collection}_{fetched_ms}_{short_id}"
        payload_path = os.path.join(bronze_root, f"{rel_base}.{ext}")
        sidecar_path = os.path.join(bronze_root, f"{rel_base}.meta.json")

        sidecar = {
            **meta,
            "source": source,
            "collection": collection,
            "fetched_at": fetched_dt.strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z",
            "fetched_at_unix_ms": fetched_ms,
            "byte_size": len(raw_bytes),
            "sha256": hashlib.sha256(raw_bytes).hexdigest(),
            "stored_encoding": stored_encoding,
            "schema_version": meta.get("schema_version", SCHEMA_VERSION),
        }
        sidecar_bytes = json.dumps(sidecar, separators=(",", ":"), sort_keys=True).encode(
            "utf-8"
        )

        # Payload first, then sidecar -- if the sidecar write fails the payload
        # is still safely on disk.
        _write_atomic(payload_path, bytes(raw_bytes))
        _write_atomic(sidecar_path, sidecar_bytes)

        logger.debug(
            "bronze capture written",
            source=source,
            collection=collection,
            path=payload_path,
            byte_size=len(raw_bytes),
        )
        return payload_path
    except Exception as e:  # noqa: BLE001 - capture must never break processing
        logger.warning(
            "bronze capture failed",
            source=source,
            collection=collection,
            error=str(e),
        )
        return None
