"""Bronze layer: immutable, append-only capture of raw source bytes.

Bronze preserves the exact bytes received from each data source so they can be
reprocessed later without re-fetching from rate-limited or non-replayable
sources. Capture is a best-effort side-effect added alongside existing
processing -- it never alters how data is parsed, transformed, or served, and a
failed capture never breaks the processor.

See ``docs/BRONZE.md`` for the full specification.
"""

from src.bronze.capture import capture_bronze, is_bronze_enabled

__all__ = ["capture_bronze", "is_bronze_enabled"]
