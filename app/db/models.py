from __future__ import annotations

from datetime import UTC, date, datetime

from sqlalchemy import Boolean, Date, DateTime, Float, ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


def utc_now() -> datetime:
    return datetime.now(UTC)


class EtfModel(Base):
    __tablename__ = "etfs"

    id: Mapped[int] = mapped_column(primary_key=True)
    asset_class: Mapped[str] = mapped_column(String(80), nullable=False)
    segment: Mapped[str] = mapped_column(String(160), nullable=False)
    name: Mapped[str] = mapped_column(String(260), nullable=False)
    isin: Mapped[str] = mapped_column(String(12), unique=True, nullable=False, index=True)
    ticker: Mapped[str | None] = mapped_column(String(40), nullable=True)
    exchange: Mapped[str] = mapped_column(String(40), default="GETTEX", nullable=False)
    currency: Mapped[str] = mapped_column(String(8), default="EUR", nullable=False)
    ter: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    target_pct: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    target_segment_pct: Mapped[float | None] = mapped_column(Float, nullable=True)
    price: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    price_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    price_source: Mapped[str] = mapped_column(String(80), default="manual", nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    holding: Mapped[HoldingModel | None] = relationship(
        back_populates="etf",
        cascade="all, delete-orphan",
        uselist=False,
    )
    prices: Mapped[list[PriceHistoryModel]] = relationship(
        back_populates="etf",
        cascade="all, delete-orphan",
    )


class HoldingModel(Base):
    __tablename__ = "holdings"

    id: Mapped[int] = mapped_column(primary_key=True)
    etf_id: Mapped[int] = mapped_column(ForeignKey("etfs.id"), unique=True, nullable=False)
    quantity: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    average_price: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=utc_now,
        onupdate=utc_now,
        nullable=False,
    )

    etf: Mapped[EtfModel] = relationship(back_populates="holding")


class PriceHistoryModel(Base):
    __tablename__ = "price_history"
    __table_args__ = (UniqueConstraint("etf_id", "date", name="uq_price_history_etf_date"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    etf_id: Mapped[int] = mapped_column(ForeignKey("etfs.id"), nullable=False, index=True)
    date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    price: Mapped[float] = mapped_column(Float, nullable=False)
    source: Mapped[str] = mapped_column(String(80), default="manual", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, nullable=False)

    etf: Mapped[EtfModel] = relationship(back_populates="prices")


class EtfMetadataCacheModel(Base):
    __tablename__ = "etf_metadata_cache"

    isin: Mapped[str] = mapped_column(String(12), primary_key=True)
    name: Mapped[str] = mapped_column(String(260), nullable=False)
    segment: Mapped[str] = mapped_column(String(160), nullable=False)
    ticker: Mapped[str | None] = mapped_column(String(40), nullable=True)
    exchange: Mapped[str] = mapped_column(String(40), default="GETTEX", nullable=False)
    currency: Mapped[str] = mapped_column(String(8), default="EUR", nullable=False)
    ter: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    price: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    price_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    price_source: Mapped[str] = mapped_column(String(80), default="justETF metadata", nullable=False)
    fetched_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=utc_now,
        onupdate=utc_now,
        nullable=False,
    )


class PacSimulationModel(Base):
    __tablename__ = "pac_simulations"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    monthly_pac: Mapped[float] = mapped_column(Float, nullable=False)
    execution_schedule: Mapped[str] = mapped_column(String(80), default="Mensile dal 2 del mese", nullable=False)
    round_up: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    real_monthly_pac: Mapped[float] = mapped_column(Float, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=utc_now,
        onupdate=utc_now,
        nullable=False,
    )
    applied_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    rows: Mapped[list[PacSimulationRowModel]] = relationship(
        back_populates="simulation",
        cascade="all, delete-orphan",
        order_by="PacSimulationRowModel.sort_order",
    )


class PacSimulationRowModel(Base):
    __tablename__ = "pac_simulation_rows"

    id: Mapped[int] = mapped_column(primary_key=True)
    simulation_id: Mapped[int] = mapped_column(ForeignKey("pac_simulations.id"), nullable=False, index=True)
    sort_order: Mapped[int] = mapped_column(default=0, nullable=False)
    asset_class: Mapped[str] = mapped_column(String(80), nullable=False)
    asset_class_pct: Mapped[float] = mapped_column(Float, nullable=False)
    segment_pct: Mapped[float] = mapped_column(Float, nullable=False)
    target_pct: Mapped[float] = mapped_column(Float, nullable=False)
    nominal_amount: Mapped[float] = mapped_column(Float, nullable=False)
    effective_amount: Mapped[float] = mapped_column(Float, nullable=False)
    isin: Mapped[str] = mapped_column(String(12), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(260), nullable=False)
    segment: Mapped[str] = mapped_column(String(160), nullable=False)
    ticker: Mapped[str | None] = mapped_column(String(40), nullable=True)
    exchange: Mapped[str] = mapped_column(String(40), default="GETTEX", nullable=False)
    currency: Mapped[str] = mapped_column(String(8), default="EUR", nullable=False)
    ter: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    price: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    price_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    price_source: Mapped[str] = mapped_column(String(80), default="justETF metadata", nullable=False)

    simulation: Mapped[PacSimulationModel] = relationship(back_populates="rows")


class PacExecutionModel(Base):
    __tablename__ = "pac_executions"
    __table_args__ = (UniqueConstraint("simulation_id", "execution_date", name="uq_pac_execution_sim_date"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    simulation_id: Mapped[int | None] = mapped_column(nullable=True, index=True)
    simulation_name: Mapped[str] = mapped_column(String(120), nullable=False)
    execution_schedule: Mapped[str] = mapped_column(String(80), nullable=False)
    name: Mapped[str] = mapped_column(String(180), nullable=False)
    execution_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    manual: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=utc_now,
        onupdate=utc_now,
        nullable=False,
    )

    rows: Mapped[list[PacExecutionRowModel]] = relationship(
        back_populates="execution",
        cascade="all, delete-orphan",
        order_by="PacExecutionRowModel.sort_order",
    )


class PacExecutionRowModel(Base):
    __tablename__ = "pac_execution_rows"

    id: Mapped[int] = mapped_column(primary_key=True)
    execution_id: Mapped[int] = mapped_column(ForeignKey("pac_executions.id"), nullable=False, index=True)
    sort_order: Mapped[int] = mapped_column(default=0, nullable=False)
    asset_class: Mapped[str] = mapped_column(String(80), nullable=False)
    segment: Mapped[str] = mapped_column(String(160), nullable=False)
    name: Mapped[str] = mapped_column(String(260), nullable=False)
    isin: Mapped[str] = mapped_column(String(12), nullable=False, index=True)
    invested_amount: Mapped[float] = mapped_column(Float, nullable=False)
    currency: Mapped[str] = mapped_column(String(8), default="EUR", nullable=False)
    share_price: Mapped[float | None] = mapped_column(Float, nullable=True)
    shares: Mapped[float | None] = mapped_column(Float, nullable=True)
    current_price: Mapped[float | None] = mapped_column(Float, nullable=True)
    current_price_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    current_price_source: Mapped[str] = mapped_column(String(80), default="", nullable=False)
    previous_price: Mapped[float | None] = mapped_column(Float, nullable=True)
    price_diff: Mapped[float | None] = mapped_column(Float, nullable=True)
    price_diff_pct: Mapped[float | None] = mapped_column(Float, nullable=True)

    execution: Mapped[PacExecutionModel] = relationship(back_populates="rows")


class PortfolioSnapshotModel(Base):
    __tablename__ = "portfolio_snapshots"

    id: Mapped[int] = mapped_column(primary_key=True)
    date: Mapped[date] = mapped_column(Date, unique=True, nullable=False, index=True)
    total_value: Mapped[float] = mapped_column(Float, nullable=False)
    equity_value: Mapped[float] = mapped_column(Float, nullable=False)
    bond_value: Mapped[float] = mapped_column(Float, nullable=False)
    alternative_value: Mapped[float] = mapped_column(Float, nullable=False)
    monthly_diff: Mapped[float | None] = mapped_column(Float, nullable=True)
    yearly_diff: Mapped[float | None] = mapped_column(Float, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, nullable=False)


class SettingModel(Base):
    __tablename__ = "settings"

    key: Mapped[str] = mapped_column(String(80), primary_key=True)
    value: Mapped[str] = mapped_column(String(260), nullable=False)
