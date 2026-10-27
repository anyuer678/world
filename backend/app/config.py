from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parent.parent


@dataclass(frozen=True)
class Settings:
    db_path: str
    max_workers: int
    default_max_steps: int
    max_wall_seconds: float
    event_log_size: int
    zero_delay_chain_limit: int
    cancel_poll_interval: int

    @staticmethod
    def from_env() -> "Settings":
        return Settings(
            db_path=os.environ.get(
                "WORLDLAB_DB", str(BACKEND_ROOT / "data" / "worldlab.db")
            ),
            max_workers=int(os.environ.get("WORLDLAB_MAX_WORKERS", "2")),
            default_max_steps=int(os.environ.get("WORLDLAB_DEFAULT_MAX_STEPS", "1000000")),
            max_wall_seconds=float(os.environ.get("WORLDLAB_MAX_WALL_SECONDS", "120")),
            event_log_size=int(os.environ.get("WORLDLAB_EVENT_LOG_SIZE", "500")),
            zero_delay_chain_limit=int(os.environ.get("WORLDLAB_ZERO_DELAY_CHAIN_LIMIT", "10000")),
            cancel_poll_interval=int(os.environ.get("WORLDLAB_CANCEL_POLL_INTERVAL", "256")),
        )


default_settings = Settings.from_env()
