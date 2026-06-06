from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime

LEGACY_PAC_EXECUTION_SCHEDULE = "Mensile dal 1 del mese"
DEFAULT_PAC_EXECUTION_SCHEDULE = "Mensile dal 2 del mese"
PAC_EXECUTION_SCHEDULE_OPTIONS = (
    "Settimanale dal 2 del mese",
    "Settimanale dal 16 del mese",
    "2 volte al mese dal 2 del mese",
    "2 volte al mese dal 16 del mese",
    DEFAULT_PAC_EXECUTION_SCHEDULE,
    "Mensile dal 16 del mese",
    "Ogni 3 mesi dal 2 del mese",
    "Ogni 3 mesi dal 16 del mese",
)


@dataclass(slots=True)
class PortfolioPosition:
    etf_id: int
    asset_class: str
    segment: str
    name: str
    isin: str
    ticker: str | None
    exchange: str
    currency: str
    ter: float
    target_pct: float
    target_segment_pct: float | None
    quantity: float
    average_price: float
    price: float
    price_date: date | None
    price_source: str
    enabled: bool = True

    @property
    def current_value(self) -> float:
        return self.quantity * self.price


@dataclass(slots=True)
class AllocationRow:
    position: PortfolioPosition
    current_value: float
    current_weight: float
    target_value: float
    drift_value: float
    drift_pct: float
    monthly_pac_amount: float
    annual_ter_cost: float


@dataclass(slots=True)
class AssetClassSummary:
    asset_class: str
    target_pct: float
    value: float
    current_weight: float
    drift_pct: float


@dataclass(slots=True)
class AllocationSummary:
    total_value: float
    weighted_ter: float
    rows: list[AllocationRow]
    asset_classes: dict[str, AssetClassSummary]
    latest_price_date: date | None


@dataclass(slots=True)
class RebalanceRow:
    position: PortfolioPosition
    target_pct: float
    current_weight: float
    drift_value: float
    drift_pct: float
    buy_amount: float
    estimated_units: float


@dataclass(slots=True)
class PortfolioSnapshot:
    date: date
    total_value: float
    equity_value: float
    bond_value: float
    alternative_value: float
    monthly_diff: float | None = None
    yearly_diff: float | None = None


@dataclass(slots=True)
class PeriodStarts:
    current: date
    previous_month: date
    year_start: date
    previous_year: date


@dataclass(slots=True)
class PerformanceReport:
    current: PortfolioSnapshot | None
    previous_month: PortfolioSnapshot | None
    year_start: PortfolioSnapshot | None
    previous_year: PortfolioSnapshot | None
    monthly_diff: float | None
    monthly_diff_pct: float | None
    ytd_diff: float | None
    ytd_diff_pct: float | None
    yearly_diff: float | None
    yearly_diff_pct: float | None


@dataclass(slots=True)
class PriceQuote:
    isin: str
    price: float
    price_date: date
    source: str
    currency: str = "EUR"


@dataclass(slots=True)
class HistoricalPriceQuote:
    isin: str
    price: float
    price_date: date
    source: str
    currency: str = "EUR"


@dataclass(slots=True)
class PriceUpdateResult:
    isin: str
    ok: bool
    price: float | None
    source: str
    message: str


@dataclass(slots=True)
class EtfMetadata:
    isin: str
    name: str
    segment: str
    ticker: str | None
    exchange: str
    currency: str
    ter: float
    price: float
    price_date: date | None
    price_source: str


@dataclass(frozen=True, slots=True)
class PacEtfAllocation:
    asset_class: str
    isin: str
    segment_pct: float


@dataclass(slots=True)
class PacSimulationRow:
    asset_class: str
    asset_class_pct: float
    segment_pct: float
    target_pct: float
    nominal_amount: float
    effective_amount: float
    metadata: EtfMetadata


@dataclass(slots=True)
class PacSimulationPreview:
    monthly_pac: float
    round_up: bool
    real_monthly_pac: float
    rows: list[PacSimulationRow]
    execution_schedule: str = DEFAULT_PAC_EXECUTION_SCHEDULE


@dataclass(slots=True)
class SavedPacSimulation:
    id: int
    name: str
    monthly_pac: float
    round_up: bool
    real_monthly_pac: float
    created_at: datetime
    updated_at: datetime
    applied_at: datetime | None
    rows: list[PacSimulationRow]
    execution_schedule: str = DEFAULT_PAC_EXECUTION_SCHEDULE


@dataclass(slots=True)
class PacExecutionRow:
    id: int
    asset_class: str
    segment: str
    name: str
    isin: str
    invested_amount: float
    currency: str
    current_price: float | None = None
    current_price_date: date | None = None
    current_price_source: str = ""
    previous_price: float | None = None
    price_diff: float | None = None
    price_diff_pct: float | None = None


@dataclass(slots=True)
class PacExecution:
    id: int
    simulation_id: int | None
    simulation_name: str
    execution_schedule: str
    name: str
    execution_date: date
    manual: bool
    created_at: datetime
    updated_at: datetime
    rows: list[PacExecutionRow]

    @property
    def total_invested(self) -> float:
        return sum(row.invested_amount for row in self.rows)
