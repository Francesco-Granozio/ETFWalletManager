from __future__ import annotations

from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

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
    from app.db.repositories import PortfolioRepository

    with session_factory() as session:
        repo = PortfolioRepository(session)
        repo.ensure_default_settings()
        repo.ensure_simulation_from_active_portfolio()
        session.commit()
