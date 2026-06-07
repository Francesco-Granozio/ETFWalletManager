from __future__ import annotations

from enum import StrEnum

from app.domain import (
    DashboardSnapshot,
    DashboardSnapshotRow,
    PacSimulationRow,
    PortfolioPosition,
    RebalanceOperation,
    RebalancePlan,
    RebalancePlanRow,
    RebalanceRow,
    SavedPacSimulation,
)


class RebalanceMode(StrEnum):
    PROPORTIONAL_TARGET = "Compra proporzionale al target"
    ONLY_UNDERWEIGHT = "Compra ETF sottopesati"
    MOST_UNDERWEIGHT = "Compra il piu sottopesato"
    MAX_TWO_UNDERWEIGHT = "Compra massimo 2 sottopesati"


DRIFT_TOLERANCE = 0.005
ASSET_CLASS_ORDER = ("Azioni", "Obbligazioni", "Alternativi")


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


def calculate_rebalance_plan(
    snapshot: DashboardSnapshot,
    simulation: SavedPacSimulation,
    mode: RebalanceMode = RebalanceMode.ONLY_UNDERWEIGHT,
    overrides: dict[str, str] | None = None,
) -> RebalancePlan:
    selected_overrides = {
        isin.strip().upper(): value.strip().lower()
        for isin, value in (overrides or {}).items()
        if isin.strip()
    }
    target_by_isin = {
        row.metadata.isin.strip().upper(): row
        for row in simulation.rows
        if row.metadata.isin.strip()
    }
    snapshot_by_isin = {
        row.isin.strip().upper(): row
        for row in snapshot.rows
        if row.isin.strip()
    }
    total_current_value = sum(
        row.current_value
        for row in snapshot_by_isin.values()
        if row.current_value is not None and not row.missing_data
    )

    base_rows: list[dict[str, object]] = []
    for isin in _ordered_isins(target_by_isin, snapshot_by_isin):
        target = target_by_isin.get(isin)
        current = snapshot_by_isin.get(isin)
        row = _plan_base_row(
            isin=isin,
            target=target,
            current=current,
            total_current_value=total_current_value,
            override=selected_overrides.get(isin, "auto"),
        )
        base_rows.append(row)

    buy_amounts = _plan_buy_amounts(base_rows, simulation.real_monthly_pac, mode)
    plan_rows: list[RebalancePlanRow] = []
    operations: list[RebalanceOperation] = []
    warnings: list[str] = []
    for base, buy_amount in zip(base_rows, buy_amounts, strict=True):
        price = base["price"]
        estimated_units = (
            round(buy_amount / float(price), 6)
            if buy_amount > 0 and isinstance(price, (float, int)) and price > 0
            else None
        )
        plan_row = RebalancePlanRow(
            asset_class=str(base["asset_class"]),
            segment=str(base["segment"]),
            name=str(base["name"]),
            isin=str(base["isin"]),
            target_pct=float(base["target_pct"]),
            current_value=base["current_value"] if isinstance(base["current_value"], (float, int)) else None,
            current_weight=base["current_weight"] if isinstance(base["current_weight"], (float, int)) else None,
            drift_value=base["drift_value"] if isinstance(base["drift_value"], (float, int)) else None,
            drift_pct=base["drift_pct"] if isinstance(base["drift_pct"], (float, int)) else None,
            status=str(base["status"]),
            action=str(base["action_label"]),
            buy_amount=round(buy_amount, 2),
            estimated_units=estimated_units,
            price=float(price) if isinstance(price, (float, int)) and price > 0 else None,
            reason=str(base["reason"]),
        )
        plan_rows.append(plan_row)
        if plan_row.status == "Non calcolabile":
            warnings.append(f"{plan_row.isin}: dati dashboard incompleti, escluso dal piano.")
        if plan_row.buy_amount > 0:
            operations.append(
                RebalanceOperation(
                    asset_class=plan_row.asset_class,
                    segment=plan_row.segment,
                    name=plan_row.name,
                    isin=plan_row.isin,
                    buy_amount=plan_row.buy_amount,
                    estimated_units=plan_row.estimated_units,
                    reason=plan_row.reason,
                )
            )

    return RebalancePlan(
        simulation_id=simulation.id,
        simulation_name=simulation.name,
        snapshot_id=snapshot.id,
        snapshot_captured_at=snapshot.captured_at,
        latest_live_price_date=snapshot.latest_live_price_date,
        budget=round(simulation.real_monthly_pac, 2),
        total_current_value=round(total_current_value, 2),
        underweight_count=sum(1 for row in plan_rows if row.status == "Sottopesato"),
        overweight_count=sum(1 for row in plan_rows if row.status == "Sovrappesato"),
        rows=plan_rows,
        operations=operations,
        warnings=warnings,
    )


def _ordered_isins(
    target_by_isin: dict[str, PacSimulationRow],
    snapshot_by_isin: dict[str, DashboardSnapshotRow],
) -> list[str]:
    isins = set(target_by_isin) | set(snapshot_by_isin)

    def key(isin: str) -> tuple[int, str, str]:
        target = target_by_isin.get(isin)
        current = snapshot_by_isin.get(isin)
        asset_class = target.asset_class if target is not None else current.asset_class if current else ""
        segment = target.metadata.segment if target is not None else current.segment if current else ""
        try:
            asset_index = ASSET_CLASS_ORDER.index(asset_class)
        except ValueError:
            asset_index = len(ASSET_CLASS_ORDER)
        return (asset_index, segment.lower(), isin)

    return sorted(isins, key=key)


def _plan_base_row(
    isin: str,
    target: PacSimulationRow | None,
    current: DashboardSnapshotRow | None,
    total_current_value: float,
    override: str,
) -> dict[str, object]:
    target_pct = target.target_pct if target is not None else 0.0
    current_value = current.current_value if current is not None else 0.0
    current_weight = (
        current_value / total_current_value
        if current_value is not None and total_current_value > 0
        else 0.0
    )
    target_value = total_current_value * target_pct
    missing_data = current.missing_data if current is not None else False
    if current is not None and (current.current_value is None or missing_data):
        current_value = None
        current_weight = None
        drift_value = None
        drift_pct = None
        status = "Non calcolabile"
        reason = "Dati dashboard incompleti"
    else:
        drift_value = float(current_value) - target_value
        drift_pct = float(current_weight) - target_pct
        if drift_pct < -DRIFT_TOLERANCE:
            status = "Sottopesato"
            reason = "Deficit rispetto al target"
        elif drift_pct > DRIFT_TOLERANCE:
            status = "Sovrappesato"
            reason = "Sopra target, nessun acquisto"
        else:
            status = "In linea"
            reason = "Vicino al target"

    action_label = _action_label(override)
    deficit = max(0.0, target_value - float(current_value or 0)) if status != "Non calcolabile" else 0.0
    if override == "exclude":
        reason = "Escluso manualmente"
    elif override == "include":
        reason = "Incluso manualmente"
        if status != "Non calcolabile" and deficit <= 0 and target_pct > 0:
            deficit = target_value

    return {
        "asset_class": target.asset_class if target is not None else current.asset_class if current else "",
        "segment": target.metadata.segment if target is not None else current.segment if current else "",
        "name": target.metadata.name if target is not None else current.name if current else isin,
        "isin": isin,
        "target_pct": target_pct,
        "current_value": current_value,
        "current_weight": current_weight,
        "drift_value": drift_value,
        "drift_pct": drift_pct,
        "status": status,
        "action": override,
        "action_label": action_label,
        "deficit": deficit,
        "target_weight": target_pct,
        "price": _plan_price(target, current),
        "reason": reason,
    }


def _plan_buy_amounts(
    base_rows: list[dict[str, object]],
    budget: float,
    mode: RebalanceMode,
) -> list[float]:
    if not base_rows or budget <= 0:
        return [0 for _ in base_rows]

    if mode == RebalanceMode.PROPORTIONAL_TARGET:
        return _allocate_by_target(base_rows, budget)

    rows = _eligible_underweight_rows(base_rows)
    if mode == RebalanceMode.MOST_UNDERWEIGHT:
        rows = _limit_plan_rows(rows, limit=1)
    elif mode == RebalanceMode.MAX_TWO_UNDERWEIGHT:
        rows = _limit_plan_rows(rows, limit=2)

    total_deficit = sum(float(row["deficit"]) for row in rows)
    if total_deficit <= 0:
        return _allocate_by_target(base_rows, budget)

    selected = {str(row["isin"]): float(row["deficit"]) for row in rows}
    return [
        round(budget * selected.get(str(row["isin"]), 0.0) / total_deficit, 2)
        for row in base_rows
    ]


def _eligible_underweight_rows(base_rows: list[dict[str, object]]) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for row in base_rows:
        action = row["action"]
        if action == "exclude" or row["status"] == "Non calcolabile":
            continue
        if row["status"] == "Sottopesato" or action == "include":
            rows.append(row)
    return rows


def _limit_plan_rows(
    rows: list[dict[str, object]],
    limit: int,
) -> list[dict[str, object]]:
    return sorted(rows, key=lambda row: float(row["deficit"]), reverse=True)[:limit]


def _allocate_by_target(base_rows: list[dict[str, object]], budget: float) -> list[float]:
    eligible = [
        row
        for row in base_rows
        if row["action"] != "exclude"
        and row["status"] != "Non calcolabile"
        and float(row["target_weight"]) > 0
    ]
    total_weight = sum(float(row["target_weight"]) for row in eligible)
    if total_weight <= 0:
        return [0 for _ in base_rows]
    selected = {
        str(row["isin"]): float(row["target_weight"])
        for row in eligible
    }
    return [
        round(budget * selected.get(str(row["isin"]), 0.0) / total_weight, 2)
        for row in base_rows
    ]


def _action_label(action: str) -> str:
    if action == "exclude":
        return "Escludi"
    if action == "include":
        return "Includi"
    return "Auto"


def _plan_price(
    target: PacSimulationRow | None,
    current: DashboardSnapshotRow | None,
) -> float | None:
    if current is not None and current.live_price is not None and current.live_price > 0:
        return current.live_price
    if target is not None and target.metadata.price > 0:
        return target.metadata.price
    return None


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
