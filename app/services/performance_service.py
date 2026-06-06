from __future__ import annotations

from datetime import date
from typing import Protocol

from app.domain import PerformanceReport, PeriodStarts, PortfolioPosition, PortfolioSnapshot


class SnapshotRepository(Protocol):
    def get_snapshot(self, snapshot_date: date) -> PortfolioSnapshot | None: ...

    def save_snapshot(self, snapshot: PortfolioSnapshot) -> PortfolioSnapshot: ...

    def list_snapshots(self) -> list[PortfolioSnapshot]: ...


def period_starts(today: date) -> PeriodStarts:
    current = date(today.year, today.month, 1)
    if today.month == 1:
        previous_month = date(today.year - 1, 12, 1)
    else:
        previous_month = date(today.year, today.month - 1, 1)
    return PeriodStarts(
        current=current,
        previous_month=previous_month,
        year_start=date(today.year, 1, 1),
        previous_year=date(today.year - 1, today.month, 1),
    )


class PerformanceService:
    def __init__(self, repository: SnapshotRepository):
        self.repository = repository

    def build_report(self, today: date) -> PerformanceReport:
        periods = period_starts(today)
        current = self.repository.get_snapshot(periods.current)
        previous_month = self.repository.get_snapshot(periods.previous_month)
        year_start = self.repository.get_snapshot(periods.year_start)
        previous_year = self.repository.get_snapshot(periods.previous_year)

        monthly_diff, monthly_diff_pct = _diff(current, previous_month)
        ytd_diff, ytd_diff_pct = _diff(current, year_start)
        yearly_diff, yearly_diff_pct = _diff(current, previous_year)
        return PerformanceReport(
            current=current,
            previous_month=previous_month,
            year_start=year_start,
            previous_year=previous_year,
            monthly_diff=monthly_diff,
            monthly_diff_pct=monthly_diff_pct,
            ytd_diff=ytd_diff,
            ytd_diff_pct=ytd_diff_pct,
            yearly_diff=yearly_diff,
            yearly_diff_pct=yearly_diff_pct,
        )

    def create_snapshot(
        self,
        snapshot_date: date,
        positions: list[PortfolioPosition],
        price_lookup: callable | None = None,
    ) -> PortfolioSnapshot:
        existing = self.repository.get_snapshot(snapshot_date)
        if existing:
            return existing

        equity_value = 0.0
        bond_value = 0.0
        alternative_value = 0.0
        for position in positions:
            price = price_lookup(position, snapshot_date) if price_lookup else position.price
            value = position.quantity * price
            normalized = position.asset_class.lower()
            if normalized.startswith("azion"):
                equity_value += value
            elif normalized.startswith("obblig"):
                bond_value += value
            else:
                alternative_value += value

        snapshot = PortfolioSnapshot(
            date=snapshot_date,
            total_value=equity_value + bond_value + alternative_value,
            equity_value=equity_value,
            bond_value=bond_value,
            alternative_value=alternative_value,
        )
        return self.repository.save_snapshot(snapshot)

    def ensure_current_month_snapshot(
        self,
        today: date,
        positions: list[PortfolioPosition],
        price_lookup: callable | None = None,
    ) -> PortfolioSnapshot:
        return self.create_snapshot(period_starts(today).current, positions, price_lookup)


def _diff(
    current: PortfolioSnapshot | None,
    previous: PortfolioSnapshot | None,
) -> tuple[float | None, float | None]:
    if not current or not previous:
        return None, None
    value = current.total_value - previous.total_value
    pct = value / previous.total_value if previous.total_value else None
    return value, pct
