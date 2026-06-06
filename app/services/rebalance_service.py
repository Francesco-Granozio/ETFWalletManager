from __future__ import annotations

from enum import StrEnum

from app.domain import PortfolioPosition, RebalanceRow


class RebalanceMode(StrEnum):
    PROPORTIONAL_TARGET = "Compra proporzionale al target"
    ONLY_UNDERWEIGHT = "Compra ETF sottopesati"
    MOST_UNDERWEIGHT = "Compra il piu sottopesato"
    MAX_TWO_UNDERWEIGHT = "Compra massimo 2 sottopesati"


def calculate_rebalance(
    positions: list[PortfolioPosition],
    monthly_pac: float,
    mode: RebalanceMode = RebalanceMode.ONLY_UNDERWEIGHT,
) -> list[RebalanceRow]:
    total_value = sum(position.current_value for position in positions)
    base_rows = [_base_row(position, total_value) for position in positions]
    buy_amounts = _buy_amounts(base_rows, monthly_pac, mode)

    rows: list[RebalanceRow] = []
    for base, buy_amount in zip(base_rows, buy_amounts, strict=True):
        position = base["position"]
        estimated_units = buy_amount / position.price if position.price else 0
        rows.append(
            RebalanceRow(
                position=position,
                target_pct=position.target_pct,
                current_weight=base["current_weight"],
                drift_value=base["current_value"] - base["target_value"],
                drift_pct=base["current_weight"] - position.target_pct,
                buy_amount=round(buy_amount, 2),
                estimated_units=round(estimated_units, 6),
            )
        )
    return rows


def _base_row(position: PortfolioPosition, total_value: float) -> dict[str, object]:
    current_value = position.current_value
    target_value = total_value * position.target_pct
    current_weight = current_value / total_value if total_value else 0
    deficit = max(0, target_value - current_value)
    return {
        "position": position,
        "current_value": current_value,
        "target_value": target_value,
        "current_weight": current_weight,
        "deficit": deficit,
    }


def _buy_amounts(
    base_rows: list[dict[str, object]],
    monthly_pac: float,
    mode: RebalanceMode,
) -> list[float]:
    if not base_rows:
        return []

    if mode == RebalanceMode.PROPORTIONAL_TARGET:
        return [monthly_pac * row["position"].target_pct for row in base_rows]

    if mode == RebalanceMode.MOST_UNDERWEIGHT:
        return _allocate_to_largest_deficits(base_rows, monthly_pac, limit=1)

    if mode == RebalanceMode.MAX_TWO_UNDERWEIGHT:
        return _allocate_to_largest_deficits(base_rows, monthly_pac, limit=2)

    return _allocate_to_deficits(base_rows, monthly_pac)


def _allocate_to_largest_deficits(
    base_rows: list[dict[str, object]],
    monthly_pac: float,
    limit: int,
) -> list[float]:
    selected = sorted(
        enumerate(base_rows),
        key=lambda item: item[1]["deficit"],
        reverse=True,
    )[:limit]
    selected_indexes = {index for index, row in selected if row["deficit"] > 0}
    scoped_rows = [
        row if index in selected_indexes else {**row, "deficit": 0}
        for index, row in enumerate(base_rows)
    ]
    return _allocate_to_deficits(scoped_rows, monthly_pac)


def _allocate_to_deficits(base_rows: list[dict[str, object]], monthly_pac: float) -> list[float]:
    total_deficit = sum(float(row["deficit"]) for row in base_rows)
    if total_deficit <= 0:
        return [monthly_pac * row["position"].target_pct for row in base_rows]
    return [monthly_pac * float(row["deficit"]) / total_deficit for row in base_rows]
