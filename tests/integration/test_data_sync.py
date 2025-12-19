"""Integration tests for data synchronization.

These tests verify the end-to-end data sync flow from API to database.
"""

import pytest
import respx
import httpx
from datetime import datetime, timezone, timedelta
from unittest.mock import patch, AsyncMock

from src.services.data_collector import DataCollector
from src.services.sleep_service import SleepService
from src.api.whoop_client import WhoopClient
from src.models.db_models import SleepRecord, RecoveryRecord, WorkoutRecord, CycleRecord, SyncStatus


@pytest.mark.integration
@pytest.mark.asyncio
class TestDataSyncIntegration:
    """Integration tests for complete data sync flow."""

    @respx.mock
    async def test_end_to_end_sleep_sync(
        self,
        db_session,
        test_user,
        test_oauth_token,
        mock_whoop_sleep_response,
    ):
        """Test complete sleep sync from API to database."""
        client = WhoopClient(user_id=test_user.id)
        service = SleepService(user_id=test_user.id, whoop_client=client)

        # Mock token retrieval
        with patch.object(
            client.token_manager,
            "get_valid_token",
            new=AsyncMock(return_value=test_oauth_token.access_token),
        ):
            # Mock rate limiter
            with patch.object(client.rate_limiter, "acquire", new=AsyncMock()):
                # Mock API response
                respx.get(f"{client.base_url}/developer/v1/activity/sleep").mock(
                    return_value=httpx.Response(200, json=mock_whoop_sleep_response)
                )

                # Mock database context - need to commit on __exit__
                def mock_exit(*args):
                    db_session.commit()
                    return None

                with patch("src.services.sleep_service.get_db_context") as mock_context:
                    mock_context.return_value.__enter__.return_value = db_session
                    mock_context.return_value.__exit__ = mock_exit

                    # Perform sync
                    records_synced = await service.sync_sleep_records()

                    assert records_synced == 1

                    # Verify record in database
                    sleep_records = db_session.query(SleepRecord).filter_by(
                        user_id=test_user.id
                    ).all()
                    assert len(sleep_records) == 1
                    assert sleep_records[0].sleep_performance_percentage == 85.5

                    # Verify sync status
                    sync_status = db_session.query(SyncStatus).filter_by(
                        user_id=test_user.id, data_type="sleep"
                    ).first()
                    assert sync_status is not None
                    assert sync_status.status == "success"
                    assert sync_status.records_fetched == 1

    @respx.mock
    async def test_upsert_behavior(
        self,
        db_session,
        test_user,
        test_oauth_token,
        mock_whoop_sleep_response,
    ):
        """Test that sync performs upsert (updates existing records)."""
        client = WhoopClient(user_id=test_user.id)
        service = SleepService(user_id=test_user.id, whoop_client=client)

        # Modify response to have known ID
        sleep_id = mock_whoop_sleep_response["records"][0]["id"]
        mock_whoop_sleep_response["records"][0]["score"]["sleep_performance_percentage"] = 80.0

        with patch.object(
            client.token_manager,
            "get_valid_token",
            new=AsyncMock(return_value=test_oauth_token.access_token),
        ):
            with patch.object(client.rate_limiter, "acquire", new=AsyncMock()):
                # Mock database context - need to commit on __exit__
                def mock_exit(*args):
                    db_session.commit()
                    return None

                with patch("src.services.sleep_service.get_db_context") as mock_context:
                    mock_context.return_value.__enter__.return_value = db_session
                    mock_context.return_value.__exit__ = mock_exit

                    # First sync - return response with 80.0
                    route = respx.get(f"{client.base_url}/developer/v1/activity/sleep")
                    route.mock(return_value=httpx.Response(200, json=mock_whoop_sleep_response))

                    await service.sync_sleep_records()

                    # Update score in response
                    mock_whoop_sleep_response["records"][0]["score"]["sleep_performance_percentage"] = 90.0

                    # Second sync - return response with 90.0 (even with start parameter)
                    route.mock(return_value=httpx.Response(200, json=mock_whoop_sleep_response))

                    await service.sync_sleep_records()

                    # Refresh to get latest data
                    db_session.expire_all()

                    # Should still have only 1 record
                    sleep_records = db_session.query(SleepRecord).filter_by(
                        user_id=test_user.id
                    ).all()
                    assert len(sleep_records) == 1

                    # But with updated value
                    assert sleep_records[0].sleep_performance_percentage == 90.0

    @respx.mock
    async def test_full_data_collector_sync(
        self,
        db_session,
        test_user,
        test_oauth_token,
        mock_whoop_sleep_response,
        mock_whoop_recovery_response,
        mock_whoop_workout_response,
        mock_whoop_cycle_response,
    ):
        """Test syncing all data types through DataCollector."""
        collector = DataCollector(user_id=test_user.id)

        with patch.object(
            collector.token_manager,
            "get_valid_token",
            new=AsyncMock(return_value=test_oauth_token.access_token),
        ):
            with patch.object(collector.rate_limiter, "acquire", new=AsyncMock()):
                # Mock all API endpoints
                respx.get(f"{collector.whoop_client.base_url}/developer/v1/activity/sleep").mock(
                    return_value=httpx.Response(200, json=mock_whoop_sleep_response)
                )
                respx.get(f"{collector.whoop_client.base_url}/developer/v1/recovery").mock(
                    return_value=httpx.Response(200, json=mock_whoop_recovery_response)
                )
                respx.get(f"{collector.whoop_client.base_url}/developer/v1/activity/workout").mock(
                    return_value=httpx.Response(200, json=mock_whoop_workout_response)
                )
                respx.get(f"{collector.whoop_client.base_url}/developer/v1/cycle").mock(
                    return_value=httpx.Response(200, json=mock_whoop_cycle_response)
                )

                # Mock database contexts for all services
                with patch("src.services.sleep_service.get_db_context") as mock_sleep:
                    with patch("src.services.recovery_service.get_db_context") as mock_recovery:
                        with patch("src.services.workout_service.get_db_context") as mock_workout:
                            with patch("src.services.cycle_service.get_db_context") as mock_cycle:
                                for mock_ctx in [mock_sleep, mock_recovery, mock_workout, mock_cycle]:
                                    mock_ctx.return_value.__enter__.return_value = db_session
                                    mock_ctx.return_value.__exit__.return_value = None

                                # Perform full sync
                                results = await collector.sync_all_data()

                                assert results["total_records"] == 4
                                assert results["total_errors"] == 0
                                assert results["results"]["sleep"]["status"] == "success"
                                assert results["results"]["recovery"]["status"] == "success"
                                assert results["results"]["workout"]["status"] == "success"
                                assert results["results"]["cycle"]["status"] == "success"

                                # Verify all records in database
                                assert db_session.query(SleepRecord).count() == 1
                                assert db_session.query(RecoveryRecord).count() == 1
                                assert db_session.query(WorkoutRecord).count() == 1
                                assert db_session.query(CycleRecord).count() == 1

    @respx.mock
    async def test_incremental_sync(
        self,
        db_session,
        test_user,
        test_oauth_token,
        mock_whoop_sleep_response,
    ):
        """Test incremental sync using last_record_time."""
        client = WhoopClient(user_id=test_user.id)
        service = SleepService(user_id=test_user.id, whoop_client=client)

        # Create initial sync status
        sync_status = SyncStatus(
            user_id=test_user.id,
            data_type="sleep",
            last_sync_time=datetime.now(timezone.utc) - timedelta(hours=1),
            last_record_time=datetime.now(timezone.utc) - timedelta(days=1),
            status="success",
            records_fetched=10,
        )
        db_session.add(sync_status)
        db_session.commit()

        with patch.object(
            client.token_manager,
            "get_valid_token",
            new=AsyncMock(return_value=test_oauth_token.access_token),
        ):
            with patch.object(client.rate_limiter, "acquire", new=AsyncMock()):
                route = respx.get(f"{client.base_url}/developer/v1/activity/sleep")
                route.mock(
                    return_value=httpx.Response(200, json=mock_whoop_sleep_response)
                )

                with patch("src.services.sleep_service.get_db_context") as mock_context:
                    mock_context.return_value.__enter__.return_value = db_session
                    mock_context.return_value.__exit__.return_value = None

                    # Sync without explicit start time (should use last_record_time)
                    await service.sync_sleep_records()

                    # Verify API was called with start parameter
                    request = route.calls.last.request
                    assert "start" in str(request.url)

    @respx.mock
    async def test_sync_error_handling(
        self,
        db_session,
        test_user,
        test_oauth_token,
    ):
        """Test error handling during sync."""
        client = WhoopClient(user_id=test_user.id)
        service = SleepService(user_id=test_user.id, whoop_client=client)

        with patch.object(
            client.token_manager,
            "get_valid_token",
            new=AsyncMock(return_value=test_oauth_token.access_token),
        ):
            with patch.object(client.rate_limiter, "acquire", new=AsyncMock()):
                # Mock API error
                respx.get(f"{client.base_url}/developer/v1/activity/sleep").mock(
                    return_value=httpx.Response(500, json={"error": "Internal server error"})
                )

                # Mock database context - need to commit on __exit__
                def mock_exit(*args):
                    db_session.commit()
                    return None

                with patch("src.services.sleep_service.get_db_context") as mock_context:
                    mock_context.return_value.__enter__.return_value = db_session
                    mock_context.return_value.__exit__ = mock_exit

                    # Sync should raise error
                    with pytest.raises(Exception):
                        await service.sync_sleep_records()

                    # Verify error was logged in sync status
                    sync_status = db_session.query(SyncStatus).filter_by(
                        user_id=test_user.id, data_type="sleep"
                    ).first()
                    assert sync_status is not None
                    assert sync_status.status == "error"
                    assert sync_status.error_message is not None

    @pytest.mark.skip(reason="SQLite UUID handling issue with pagination - works in PostgreSQL")
    @respx.mock
    async def test_pagination_integration(
        self,
        db_session,
        test_user,
        test_oauth_token,
    ):
        """Test pagination handling in integration."""
        client = WhoopClient(user_id=test_user.id)
        service = SleepService(user_id=test_user.id, whoop_client=client)

        # Page 1
        page1 = {
            "records": [
                {
                    "id": "11111111-1111-1111-1111-111111111111",
                    "start": "2025-12-18T00:00:00.000Z",
                    "end": "2025-12-18T08:00:00.000Z",
                    "timezone_offset": "-05:00",
                    "nap": False,
                    "score_state": "SCORED",
                    "score": {
                        "stage_summary": {
                            "total_light_sleep_time_milli": 180000,
                            "total_slow_wave_sleep_time_milli": 120000,
                            "total_rem_sleep_time_milli": 60000,
                            "total_awake_time_milli": 30000,
                        },
                        "sleep_performance_percentage": 85.5,
                    },
                }
            ],
            "next_token": "page2_token",
        }

        # Page 2
        page2 = {
            "records": [
                {
                    "id": "22222222-2222-2222-2222-222222222222",
                    "start": "2025-12-17T00:00:00.000Z",
                    "end": "2025-12-17T08:00:00.000Z",
                    "timezone_offset": "-05:00",
                    "nap": False,
                    "score_state": "SCORED",
                    "score": {
                        "stage_summary": {
                            "total_light_sleep_time_milli": 180000,
                            "total_slow_wave_sleep_time_milli": 120000,
                            "total_rem_sleep_time_milli": 60000,
                            "total_awake_time_milli": 30000,
                        },
                        "sleep_performance_percentage": 90.0,
                    },
                }
            ],
            "next_token": None,
        }

        with patch.object(
            client.token_manager,
            "get_valid_token",
            new=AsyncMock(return_value=test_oauth_token.access_token),
        ):
            with patch.object(client.rate_limiter, "acquire", new=AsyncMock()):
                route = respx.get(f"{client.base_url}/developer/v1/activity/sleep")
                route.side_effect = [
                    httpx.Response(200, json=page1),
                    httpx.Response(200, json=page2),
                ]

                # Mock database context - need to commit on __exit__
                def mock_exit(*args):
                    db_session.commit()
                    return None

                with patch("src.services.sleep_service.get_db_context") as mock_context:
                    mock_context.return_value.__enter__.return_value = db_session
                    mock_context.return_value.__exit__ = mock_exit

                    # Sync should fetch both pages
                    records_synced = await service.sync_sleep_records()

                    assert records_synced == 2

                    # Refresh session to get latest data
                    db_session.expire_all()

                    # Verify both records in database
                    sleep_records = db_session.query(SleepRecord).filter_by(
                        user_id=test_user.id
                    ).all()
                    assert len(sleep_records) == 2
