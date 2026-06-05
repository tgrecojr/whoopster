"""Container entrypoint: run Alembic migrations, then start the app.

Replaces the previous `sh -c "alembic upgrade head && python -m src.main"` so
the container can run on a distroless runtime image that has no shell.
"""

import asyncio
import sys
from pathlib import Path

from alembic import command
from alembic.config import Config

from src.main import main as app_main
from src.utils.logging_config import configure_logging


def run_migrations() -> None:
    cfg = Config(str(Path("/app/alembic.ini")))
    command.upgrade(cfg, "head")


if __name__ == "__main__":
    # Configure structured logging before anything emits log lines so migration
    # and app output share one format and the third-party level overrides apply.
    configure_logging()
    run_migrations()
    try:
        asyncio.run(app_main())
    except KeyboardInterrupt:
        sys.exit(0)
