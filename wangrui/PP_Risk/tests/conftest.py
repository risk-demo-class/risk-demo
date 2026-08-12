"""Keep automated tests isolated from the configured MySQL database."""

import os


os.environ["DATABASE_URL"] = "sqlite+aiosqlite:///./pp_risk_test.db"
