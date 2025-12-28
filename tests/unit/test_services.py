"""Tests for data services."""

import pytest
from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch
from uuid import uuid4

from src.services.sleep_service import SleepService
from src.services.recovery_service import RecoveryService
from src.services.workout_service import WorkoutService
from src.services.cycle_service import CycleService
from src.services.data_collector import DataCollector, sync_user_data
from src.api.whoop_client import WhoopClient
from src.models.db_models import SleepRecord, RecoveryRecord, WorkoutRecord, CycleRecord, SyncStatus


@pytest.mark.unit
@pytest.mark.asyncio
class TestSleepService:
    """Tests for SleepService."""

    async def test_sleep_service_initialization(self, test_user):
        """Test sleep service initialization."""
        client = WhoopClient(user_id=test_user.id)
        service = SleepService(user_id=test_user.id, whoop_client=client)

        assert service.user_id == test_user.id
        assert service.whoop_client is client

    async def test_transform_api_record(self, test_user, mock_whoop_sleep_response):
        """Test transforming API record to database format."""
        client = WhoopClient(user_id=test_user.id)
        service = SleepService(user_id=test_user.id, whoop_client=client)

        api_record = mock_whoop_sleep_response["records"][0]
        db_record = service._transform_api_record(api_record)

        assert db_record["user_id"] == test_user.id
        assert "id" in db_record
        assert "start_time" in db_record
        assert "end_time" in db_record
        assert db_record["sleep_performance_percentage"] == 85.5
        assert db_record["raw_data"] == api_record

    async def test_sync_sleep_records(self, test_user, db_session, mock_whoop_sleep_response):
        """Test syncing sleep records."""
        client = WhoopClient(user_id=test_user.id)
        service = SleepService(user_id=test_user.id, whoop_client=client)

        # Mock client to return test data
        with patch.object(
            client,
            "get_sleep_records",
            new=AsyncMock(return_value=mock_whoop_sleep_response["records"]),
        ):
            # Mock database context - need to commit on __exit__
            def mock_exit(*args):
                db_session.commit()
                return None

            with patch("src.services.sleep_service.get_db_context") as mock_context:
                mock_context.return_value.__enter__.return_value = db_session
                mock_context.return_value.__exit__ = mock_exit

                records_synced = await service.sync_sleep_records()

                assert records_synced == 1

                # Verify sync status was created
                sync_status = (
                    db_session.query(SyncStatus)
                    .filter_by(user_id=test_user.id, data_type="sleep")
                    .first()
                )
                assert sync_status is not None
                assert sync_status.status == "success"
                assert sync_status.records_fetched == 1

    async def test_get_sleep_statistics(self, test_user, db_session, test_sleep_record):
        """Test getting sleep statistics."""
        client = WhoopClient(user_id=test_user.id)
        service = SleepService(user_id=test_user.id, whoop_client=client)

        with patch("src.services.sleep_service.get_db_context") as mock_context:
            mock_context.return_value.__enter__.return_value = db_session
            mock_context.return_value.__exit__.return_value = None

            stats = await service.get_sleep_statistics()

            assert stats["total_records"] == 1
            assert "earliest_record" in stats
            assert "latest_record" in stats


@pytest.mark.unit
@pytest.mark.asyncio
class TestRecoveryService:
    """Tests for RecoveryService."""

    async def test_recovery_service_initialization(self, test_user):
        """Test recovery service initialization."""
        client = WhoopClient(user_id=test_user.id)
        service = RecoveryService(user_id=test_user.id, whoop_client=client)

        assert service.user_id == test_user.id
        assert service.whoop_client is client

    async def test_transform_api_record(self, test_user, mock_whoop_recovery_response):
        """Test transforming recovery API record."""
        client = WhoopClient(user_id=test_user.id)
        service = RecoveryService(user_id=test_user.id, whoop_client=client)

        api_record = mock_whoop_recovery_response["records"][0]
        db_record = service._transform_api_record(api_record)

        assert db_record["user_id"] == test_user.id
        assert db_record["recovery_score"] == 75.0
        assert db_record["hrv_rmssd"] == 65.5


@pytest.mark.unit
@pytest.mark.asyncio
class TestWorkoutService:
    """Tests for WorkoutService."""

    async def test_workout_service_initialization(self, test_user):
        """Test workout service initialization."""
        client = WhoopClient(user_id=test_user.id)
        service = WorkoutService(user_id=test_user.id, whoop_client=client)

        assert service.user_id == test_user.id

    async def test_transform_api_record(self, test_user, mock_whoop_workout_response):
        """Test transforming workout API record."""
        client = WhoopClient(user_id=test_user.id)
        service = WorkoutService(user_id=test_user.id, whoop_client=client)

        api_record = mock_whoop_workout_response["records"][0]
        db_record = service._transform_api_record(api_record)

        assert db_record["user_id"] == test_user.id
        assert db_record["sport_name"] == "Running"
        assert db_record["strain_score"] == 12.5
        assert db_record["zone_two_duration"] == 1800000


@pytest.mark.unit
@pytest.mark.asyncio
class TestCycleService:
    """Tests for CycleService."""

    async def test_cycle_service_initialization(self, test_user):
        """Test cycle service initialization."""
        client = WhoopClient(user_id=test_user.id)
        service = CycleService(user_id=test_user.id, whoop_client=client)

        assert service.user_id == test_user.id

    async def test_transform_api_record(self, test_user, mock_whoop_cycle_response):
        """Test transforming cycle API record."""
        client = WhoopClient(user_id=test_user.id)
        service = CycleService(user_id=test_user.id, whoop_client=client)

        api_record = mock_whoop_cycle_response["records"][0]
        db_record = service._transform_api_record(api_record)

        assert db_record["user_id"] == test_user.id
        assert db_record["strain_score"] == 14.5
        assert db_record["kilojoules"] == 2000.0


@pytest.mark.unit
@pytest.mark.asyncio
class TestDataCollector:
    """Tests for DataCollector."""

    async def test_data_collector_initialization(self, test_user):
        """Test data collector initialization."""
        collector = DataCollector(user_id=test_user.id)

        assert collector.user_id == test_user.id
        assert collector.whoop_client is not None
        assert collector.sleep_service is not None
        assert collector.recovery_service is not None
        assert collector.workout_service is not None
        assert collector.cycle_service is not None

    async def test_sync_all_data(self, test_user):
        """Test syncing all data types."""
        collector = DataCollector(user_id=test_user.id)

        # Mock all services
        with patch.object(
            collector.sleep_service,
            "sync_sleep_records",
            new=AsyncMock(return_value=5),
        ):
            with patch.object(
                collector.recovery_service,
                "sync_recovery_records",
                new=AsyncMock(return_value=5),
            ):
                with patch.object(
                    collector.workout_service,
                    "sync_workout_records",
                    new=AsyncMock(return_value=3),
                ):
                    with patch.object(
                        collector.cycle_service,
                        "sync_cycle_records",
                        new=AsyncMock(return_value=5),
                    ):
                        results = await collector.sync_all_data()

                        assert results["user_id"] == test_user.id
                        assert results["total_records"] == 18
                        assert results["total_errors"] == 0
                        assert results["results"]["sleep"]["records_synced"] == 5
                        assert results["results"]["recovery"]["records_synced"] == 5
                        assert results["results"]["workout"]["records_synced"] == 3
                        assert results["results"]["cycle"]["records_synced"] == 5

    async def test_sync_all_data_with_errors(self, test_user):
        """Test syncing with some errors."""
        collector = DataCollector(user_id=test_user.id)

        # Mock services with one failure
        with patch.object(
            collector.sleep_service,
            "sync_sleep_records",
            new=AsyncMock(return_value=5),
        ):
            with patch.object(
                collector.recovery_service,
                "sync_recovery_records",
                new=AsyncMock(side_effect=Exception("API error")),
            ):
                with patch.object(
                    collector.workout_service,
                    "sync_workout_records",
                    new=AsyncMock(return_value=3),
                ):
                    with patch.object(
                        collector.cycle_service,
                        "sync_cycle_records",
                        new=AsyncMock(return_value=5),
                    ):
                        results = await collector.sync_all_data()

                        assert results["total_errors"] == 1
                        assert results["results"]["recovery"]["status"] == "error"
                        assert results["results"]["sleep"]["status"] == "success"

    async def test_sync_specific_data_types(self, test_user):
        """Test syncing specific data types."""
        collector = DataCollector(user_id=test_user.id)

        with patch.object(
            collector.sleep_service,
            "sync_sleep_records",
            new=AsyncMock(return_value=5),
        ):
            with patch.object(
                collector.workout_service,
                "sync_workout_records",
                new=AsyncMock(return_value=3),
            ):
                results = await collector.sync_all_data(data_types=["sleep", "workout"])

                assert "sleep" in results["results"]
                assert "workout" in results["results"]
                assert "recovery" not in results["results"]
                assert "cycle" not in results["results"]

    async def test_sync_sleep_only(self, test_user):
        """Test syncing only sleep data."""
        collector = DataCollector(user_id=test_user.id)

        with patch.object(
            collector.sleep_service,
            "sync_sleep_records",
            new=AsyncMock(return_value=10),
        ):
            count = await collector.sync_sleep()

            assert count == 10

    async def test_get_all_statistics(self, test_user):
        """Test getting all statistics."""
        collector = DataCollector(user_id=test_user.id)

        mock_stats = {"total_records": 10}

        with patch.object(
            collector.sleep_service,
            "get_sleep_statistics",
            new=AsyncMock(return_value=mock_stats),
        ):
            with patch.object(
                collector.recovery_service,
                "get_recovery_statistics",
                new=AsyncMock(return_value=mock_stats),
            ):
                with patch.object(
                    collector.workout_service,
                    "get_workout_statistics",
                    new=AsyncMock(return_value=mock_stats),
                ):
                    with patch.object(
                        collector.cycle_service,
                        "get_cycle_statistics",
                        new=AsyncMock(return_value=mock_stats),
                    ):
                        stats = await collector.get_all_statistics()

                        assert stats["user_id"] == test_user.id
                        assert stats["sleep"]["total_records"] == 10
                        assert stats["recovery"]["total_records"] == 10
                        assert stats["workout"]["total_records"] == 10
                        assert stats["cycle"]["total_records"] == 10

    async def test_verify_token(self, test_user):
        """Test verifying token."""
        collector = DataCollector(user_id=test_user.id)

        with patch.object(
            collector.token_manager,
            "is_token_valid",
            new=AsyncMock(return_value=True),
        ):
            is_valid = await collector.verify_token()

            assert is_valid is True

    async def test_sync_user_data_convenience_function(self, test_user):
        """Test convenience function for syncing user data."""
        with patch.object(
            DataCollector,
            "sync_all_data",
            new=AsyncMock(return_value={"total_records": 20}),
        ):
            result = await sync_user_data(test_user.id)

            assert result["total_records"] == 20
