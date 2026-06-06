"""Tests for the bronze layer (raw capture)."""

import hashlib
import json
import os
import re

import httpx
import pytest
import respx
from unittest.mock import AsyncMock, patch

from src.bronze import capture_bronze, is_bronze_enabled
from src.bronze.capture import _ext_for, _utc_now_ms
from src.api.whoop_client import WhoopClient, WhoopAPIError, _is_empty_pagination_terminator

# Path/filename naming standard:
# {source}/{collection}/dt=YYYY-MM-DD/{collection}_{unix_ms}_{short_id}.{ext}
NAME_RE = re.compile(
    r"^whoop/recovery/dt=\d{4}-\d{2}-\d{2}/recovery_\d+_[0-9a-f]{6}\.json$"
)

REQUIRED_SIDECAR_KEYS = {
    "source",
    "collection",
    "fetched_at",
    "fetched_at_unix_ms",
    "request_url",
    "request_params",
    "http_status",
    "content_type",
    "charset",
    "content_encoding",
    "stored_encoding",
    "byte_size",
    "sha256",
    "processor",
    "processor_version",
    "schema_version",
}


@pytest.fixture
def bronze_root(tmp_path, monkeypatch):
    """Point BRONZE_ROOT at a temp dir for the duration of a test."""
    root = tmp_path / "bronze"
    monkeypatch.setattr("src.bronze.capture.settings.bronze_root", str(root))
    return str(root)


@pytest.mark.unit
class TestBronzeHelpers:
    """Unit tests for bronze helper functions."""

    def test_ext_for_json_identity(self):
        assert _ext_for("application/json", "identity") == "json"
        assert _ext_for("application/json; charset=utf-8", "identity") == "json"

    def test_ext_for_native_gzip(self):
        assert _ext_for("text/csv", "gzip") == "csv.gz"

    def test_ext_for_unknown_falls_back_to_bin(self):
        assert _ext_for("application/octet-stream", "identity") == "bin"
        assert _ext_for(None, "identity") == "bin"

    def test_utc_now_ms_is_millis(self):
        ms = _utc_now_ms()
        # Sanity: 13-digit-ish epoch millis, well past year 2020.
        assert ms > 1_577_836_800_000

    def test_is_empty_pagination_terminator(self):
        assert _is_empty_pagination_terminator({"records": [], "next_token": None})
        assert not _is_empty_pagination_terminator({"records": [{"id": 1}]})
        # Single-object endpoints have no "records" key -> always captured.
        assert not _is_empty_pagination_terminator({"height_meter": 1.8})
        assert not _is_empty_pagination_terminator([])


@pytest.mark.unit
class TestCaptureBronze:
    """Unit tests for capture_bronze()."""

    def test_disabled_when_root_unset(self, monkeypatch):
        monkeypatch.setattr("src.bronze.capture.settings.bronze_root", None)
        assert is_bronze_enabled() is False
        assert capture_bronze("whoop", "recovery", b"{}", {}) is None

    def test_writes_payload_byte_for_byte_with_sidecar(self, bronze_root):
        raw = b'{"records": [{"id": 1}], "next_token": null}'
        meta = {
            "request_url": "https://api.prod.whoop.com/developer/v2/recovery?limit=25",
            "request_params": {"limit": "25"},
            "http_status": 200,
            "content_type": "application/json",
            "charset": "utf-8",
            "content_encoding": "identity",
            "stored_encoding": "identity",
            "processor": "whoop-ingest",
            "processor_version": "1.0.0",
        }

        path = capture_bronze("whoop", "recovery", raw, meta)

        assert path is not None
        # Payload bytes are identical to the source.
        with open(path, "rb") as fh:
            stored = fh.read()
        assert stored == raw

        # Path follows the naming standard exactly.
        rel = os.path.relpath(path, bronze_root)
        assert NAME_RE.match(rel.replace(os.sep, "/")), rel

        # Sidecar exists with required keys and verifiable integrity.
        # The payload ext is "json"; the sidecar appends ".meta.json".
        sidecar_path = re.sub(r"\.json$", ".meta.json", path)
        with open(sidecar_path, "rb") as fh:
            sidecar = json.load(fh)

        assert REQUIRED_SIDECAR_KEYS.issubset(sidecar.keys())
        assert sidecar["source"] == "whoop"
        assert sidecar["collection"] == "recovery"
        assert sidecar["http_status"] == 200
        assert sidecar["stored_encoding"] == "identity"
        assert sidecar["schema_version"] == "v1"
        assert sidecar["byte_size"] == len(raw)
        assert sidecar["sha256"] == hashlib.sha256(raw).hexdigest()
        assert sidecar["fetched_at"].endswith("Z")

    def test_sidecar_contains_no_secrets(self, bronze_root):
        """request_url/params carry no auth; nothing token-like leaks."""
        raw = b"{}"
        meta = {
            "request_url": "https://api.prod.whoop.com/developer/v2/recovery?limit=25",
            "request_params": {"limit": "25"},
            "http_status": 200,
            "content_type": "application/json",
            "content_encoding": "identity",
        }
        path = capture_bronze("whoop", "recovery", raw, meta)
        sidecar_text = open(re.sub(r"\.json$", ".meta.json", path)).read().lower()
        for needle in ("authorization", "bearer", "access_token", "secret"):
            assert needle not in sidecar_text

    def test_capture_failure_is_non_fatal(self, bronze_root):
        """A non-bytes payload must not raise -- capture is best-effort."""
        # raw_bytes as str violates the bytes invariant; must be swallowed.
        assert capture_bronze("whoop", "recovery", "not-bytes", {}) is None

    def test_each_capture_is_a_new_file(self, bronze_root):
        raw = b"{}"
        meta = {"content_type": "application/json"}
        p1 = capture_bronze("whoop", "recovery", raw, meta)
        p2 = capture_bronze("whoop", "recovery", raw, meta)
        assert p1 != p2  # unique short_id -> never overwrites


@pytest.mark.unit
@pytest.mark.asyncio
class TestWhoopClientBronzeCapture:
    """Client-level tests: capture is additive and behavior is unchanged."""

    async def _client(self, user_id):
        client = WhoopClient(user_id=user_id)
        return client

    @respx.mock
    async def test_successful_fetch_captures_and_returns_records(
        self, test_user, bronze_root, mock_whoop_recovery_response
    ):
        client = WhoopClient(user_id=test_user.id)
        with patch.object(
            client.token_manager, "get_valid_token", new=AsyncMock(return_value="tok")
        ), patch.object(client.rate_limiter, "acquire", new=AsyncMock()):
            respx.get(f"{client.base_url}/developer/v2/recovery").mock(
                return_value=httpx.Response(200, json=mock_whoop_recovery_response)
            )

            records = await client.get_recovery_records()

        # Existing behavior unchanged: records returned as before.
        assert records == mock_whoop_recovery_response["records"]

        # A bronze file was written under whoop/recovery.
        files = []
        for dirpath, _dirs, names in os.walk(bronze_root):
            files.extend(os.path.join(dirpath, n) for n in names)
        payloads = [f for f in files if f.endswith(".json") and not f.endswith(".meta.json")]
        assert len(payloads) == 1
        with open(payloads[0], "rb") as fh:
            stored = json.load(fh)
        assert stored == mock_whoop_recovery_response

        await client.aclose()

    @respx.mock
    async def test_empty_terminator_page_is_not_captured(
        self, test_user, bronze_root
    ):
        client = WhoopClient(user_id=test_user.id)
        with patch.object(
            client.token_manager, "get_valid_token", new=AsyncMock(return_value="tok")
        ), patch.object(client.rate_limiter, "acquire", new=AsyncMock()):
            respx.get(f"{client.base_url}/developer/v2/recovery").mock(
                return_value=httpx.Response(200, json={"records": [], "next_token": None})
            )

            records = await client.get_recovery_records()

        assert records == []
        # No payload written for a zero-record page.
        files = [
            n for _d, _s, names in os.walk(bronze_root) for n in names
        ]
        assert files == []
        await client.aclose()

    @respx.mock
    async def test_error_body_is_captured_with_real_status(
        self, test_user, bronze_root
    ):
        client = WhoopClient(user_id=test_user.id)
        with patch.object(
            client.token_manager, "get_valid_token", new=AsyncMock(return_value="tok")
        ), patch.object(client.rate_limiter, "acquire", new=AsyncMock()):
            respx.get(f"{client.base_url}/developer/v2/user/measurement/body").mock(
                return_value=httpx.Response(403, json={"error": "missing scope"})
            )

            # Existing behavior unchanged: a non-retryable error still raises.
            with pytest.raises(WhoopAPIError):
                await client.get_body_measurement()

        # The diagnostic error body was captured with its real status.
        sidecars = [
            os.path.join(d, n)
            for d, _s, names in os.walk(bronze_root)
            for n in names
            if n.endswith(".meta.json")
        ]
        assert len(sidecars) == 1
        meta = json.load(open(sidecars[0]))
        assert meta["http_status"] == 403
        assert meta["collection"] == "body_measurement"
        await client.aclose()

    @respx.mock
    async def test_capture_disabled_leaves_behavior_unchanged(
        self, test_user, monkeypatch, mock_whoop_recovery_response
    ):
        monkeypatch.setattr("src.bronze.capture.settings.bronze_root", None)
        client = WhoopClient(user_id=test_user.id)
        with patch.object(
            client.token_manager, "get_valid_token", new=AsyncMock(return_value="tok")
        ), patch.object(client.rate_limiter, "acquire", new=AsyncMock()):
            respx.get(f"{client.base_url}/developer/v2/recovery").mock(
                return_value=httpx.Response(200, json=mock_whoop_recovery_response)
            )
            records = await client.get_recovery_records()

        assert records == mock_whoop_recovery_response["records"]
        await client.aclose()
