from __future__ import annotations

from datetime import date

from app.domain import (
    AllocationRow,
    AllocationSummary,
    AssetClassSummary,
    PortfolioPosition,
)


def calculate_allocation(
    positions: list[PortfolioPosition],
    monthly_pac: float,
) -> AllocationSummary:
    total_value = sum(position.current_value for position in positions)
    latest_price_date = _latest_date(position.price_date for position in positions)

    rows: list[AllocationRow] = []
    for position in positions:
        current_value = position.current_value
        current_weight = current_value / total_value if total_value else 0
        target_value = total_value * position.target_pct
        drift_value = current_value - target_value
        drift_pct = current_weight - position.target_pct
        rows.append(
            AllocationRow(
                position=position,
                current_value=current_value,
                current_weight=current_weight,
                target_value=target_value,
                drift_value=drift_value,
                drift_pct=drift_pct,
                monthly_pac_amount=round(monthly_pac * position.target_pct, 2),
                annual_ter_cost=current_value * position.ter,
            )
        )

    weighted_ter = _weighted_ter(positions, total_value)
    asset_classes = _asset_class_summary(rows, total_value)
    return AllocationSummary(
        total_value=total_value,
        weighted_ter=weighted_ter,
        rows=rows,
        asset_classes=asset_classes,
        latest_price_date=latest_price_date,
    )


def _weighted_ter(positions: list[PortfolioPosition], total_value: float) -> float:
    if not positions:
        return 0
    if total_value:
        return sum((position.current_value / total_value) * position.ter for position in positions)
    return sum(position.target_pct * position.ter for position in positions)


def _asset_class_summary(
    rows: list[AllocationRow],
    total_value: float,
) -> dict[str, AssetClassSummary]:
    grouped: dict[str, tuple[float, float]] = {}
    for row in rows:
        target_pct, value = grouped.get(row.position.asset_class, (0, 0))
        grouped[row.position.asset_class] = (
            target_pct + row.position.target_pct,
            value + row.current_value,
        )

    result: dict[str, AssetClassSummary] = {}
    for asset_class, (target_pct, value) in grouped.items():
        current_weight = value / total_value if total_value else 0
        result[asset_class] = AssetClassSummary(
            asset_class=asset_class,
            target_pct=target_pct,
            value=value,
            current_weight=current_weight,
            drift_pct=current_weight - target_pct,
        )
    return result


def _latest_date(values: object) -> date | None:
    dates = [value for value in values if isinstance(value, date)]
    return max(dates) if dates else None
