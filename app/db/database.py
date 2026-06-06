from __future__ import annotations

from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy import text
from sqlalchemy.orm import Session, sessionmaker

from app.domain import DEFAULT_PAC_EXECUTION_SCHEDULE, LEGACY_PAC_EXECUTION_SCHEDULE
from app.db.models import Base

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DB_PATH = PROJECT_ROOT / "data" / "portfolio.db"


def create_session_factory(db_path: str | Path = DEFAULT_DB_PATH) -> sessionmaker[Session]:
    path = Path(db_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    engine = create_engine(f"sqlite:///{path}", future=True)
    return sessionmaker(bind=engine, expire_on_commit=False, future=True)


def init_database(session_factory: sessionmaker[Session]) -> None:
    engine = session_factory.kw["bind"]
    Base.metadata.create_all(engine)
    _migrate_database(engine)
    from app.db.repositories import PortfolioRepository

    with session_factory() as session:
        repo = PortfolioRepository(session)
        repo.ensure_default_settings()
        repo.ensure_simulation_from_active_portfolio()
        session.commit()


def _migrate_database(engine) -> None:
    with engine.begin() as connection:
        tables = {
            row[0]
            for row in connection.execute(
                text("SELECT name FROM sqlite_master WHERE type='table'")
            )
        }
        if "pac_simulations" in tables:
            columns = {
                row[1]
                for row in connection.execute(text("PRAGMA table_info(pac_simulations)"))
            }
            if "execution_schedule" not in columns:
                connection.execute(
                    text(
                        f"""
                        ALTER TABLE pac_simulations
                        ADD COLUMN execution_schedule VARCHAR(80)
                        NOT NULL DEFAULT '{DEFAULT_PAC_EXECUTION_SCHEDULE}'
                        """
                    )
                )
            else:
                connection.execute(
                    text(
                        """
                        UPDATE pac_simulations
                        SET execution_schedule = :default_schedule
                        WHERE execution_schedule = :legacy_schedule
                        """
                    ),
                    {
                        "default_schedule": DEFAULT_PAC_EXECUTION_SCHEDULE,
                        "legacy_schedule": LEGACY_PAC_EXECUTION_SCHEDULE,
                    },
                )
        if "pac_execution_rows" in tables:
            columns = {
                row[1]
                for row in connection.execute(text("PRAGMA table_info(pac_execution_rows)"))
            }
            if "share_price" not in columns:
                connection.execute(text("ALTER TABLE pac_execution_rows ADD COLUMN share_price FLOAT"))
            if "shares" not in columns:
                connection.execute(text("ALTER TABLE pac_execution_rows ADD COLUMN shares FLOAT"))
        if "settings" in tables:
            connection.execute(
                text(
                    """
                    UPDATE settings
                    SET value = :default_schedule
                    WHERE key = 'pac_execution_schedule'
                    AND value = :legacy_schedule
                    """
                ),
                {
                    "default_schedule": DEFAULT_PAC_EXECUTION_SCHEDULE,
                    "legacy_schedule": LEGACY_PAC_EXECUTION_SCHEDULE,
                },
            )
