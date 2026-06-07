from datetime import date
from datetime import datetime

from app.domain import (
    DashboardSnapshot,
    DashboardSnapshotRow,
    EtfMetadata,
    PacSimulationRow,
    PortfolioPosition,
    SavedPacSimulation,
)
from app.services.rebalance_service import (
    RebalanceMode,
    calculate_rebalance,
    calculate_rebalance_plan,
)


def position(isin: str, target_pct: float, quantity: float, price: float) -> PortfolioPosition:
    return PortfolioPosition(
        etf_id=1,
        asset_class="Azioni",
        segment="Segment",
        name=isin,
        isin=isin,
        ticker=None,
        exchange="GETTEX",
        currency="EUR",
        ter=0.001,
        target_pct=target_pct,
        target_segment_pct=None,
        quantity=quantity,
        average_price=price,
        price=price,
        price_date=date(2026, 6, 6),
        price_source="manual",
        enabled=True,
    )


def test_only_underweight_allocates_pac_proportionally_to_deficits():
    positions = [
        position("AAA", 0.50, 3, 100),  # value 300, target 500, deficit 200
        position("BBB", 0.30, 3, 100),  # value 300, target 300, deficit 0
        position("CCC", 0.20, 4, 100),  # value 400, target 200, deficit 0
    ]

    rows = calculate_rebalance(positions, monthly_pac=200, mode=RebalanceMode.ONLY_UNDERWEIGHT)

    assert rows[0].buy_amount == 200
    assert rows[0].estimated_units == 2
    assert rows[1].buy_amount == 0
    assert rows[2].buy_amount == 0


def test_only_underweight_falls_back_to_target_weights_when_no_deficits():
    positions = [
        position("AAA", 0.60, 6, 100),
        position("BBB", 0.40, 4, 100),
    ]

    rows = calculate_rebalance(positions, monthly_pac=100, mode=RebalanceMode.ONLY_UNDERWEIGHT)

    assert rows[0].buy_amount == 60
    assert rows[1].buy_amount == 40


def test_max_two_underweight_splits_only_between_two_largest_deficits():
    positions = [
        position("AAA", 0.50, 2, 100),  # deficit 300
        position("BBB", 0.30, 1, 100),  # deficit 200
        position("CCC", 0.20, 7, 100),  # no deficit
    ]

    rows = calculate_rebalance(positions, monthly_pac=100, mode=RebalanceMode.MAX_TWO_UNDERWEIGHT)

    assert rows[0].buy_amount == 60
    assert rows[1].buy_amount == 40
    assert rows[2].buy_amount == 0


def simulation() -> SavedPacSimulation:
    now = datetime(2026, 6, 8)
    return SavedPacSimulation(
        id=7,
        name="PAC bilanciato",
        monthly_pac=100,
        round_up=True,
        real_monthly_pac=102,
        created_at=now,
        updated_at=now,
        applied_at=now,
        rows=[
            simulation_row("Azioni", "AAA", "Azionario globale", 0.50, price=10),
            simulation_row("Obbligazioni", "BBB", "Bond globale", 0.30, price=20),
            simulation_row("Alternativi", "CCC", "Oro", 0.20, price=5),
        ],
    )


def simulation_row(
    asset_class: str,
    isin: str,
    segment: str,
    target_pct: float,
    price: float,
) -> PacSimulationRow:
    return PacSimulationRow(
        asset_class=asset_class,
        asset_class_pct=target_pct,
        segment_pct=1,
        target_pct=target_pct,
        nominal_amount=100 * target_pct,
        effective_amount=102 * target_pct,
        metadata=EtfMetadata(
            isin=isin,
            name=f"ETF {isin}",
            segment=segment,
            ticker=None,
            exchange="GETTEX",
            currency="EUR",
            ter=0.001,
            price=price,
            price_date=date(2026, 6, 8),
            price_source="Lang & Schwarz LSX",
        ),
    )


def snapshot() -> DashboardSnapshot:
    return DashboardSnapshot(
        id=3,
        total_invested=1_000,
        current_value=1_000,
        result_value=0,
        result_pct=0,
        latest_live_price_date=date(2026, 6, 8),
        execution_count=4,
        etf_count=4,
        quote_error_count=1,
        rows=[
            snapshot_row("Azioni", "AAA", "Azionario globale", 400, 10),
            snapshot_row("Obbligazioni", "BBB", "Bond globale", 350, 20),
            snapshot_row("Azioni", "DDD", "ETF fuori target", 250, 25),
            DashboardSnapshotRow(
                asset_class="Alternativi",
                segment="Crypto",
                name="ETF non calcolabile",
                isin="EEE",
                invested_amount=50,
                units=0,
                missing_data=True,
                live_price=None,
                live_price_date=None,
                live_price_source="",
                current_value=None,
                result_value=None,
                execution_count=1,
            ),
        ],
    )


def snapshot_row(
    asset_class: str,
    isin: str,
    segment: str,
    current_value: float,
    price: float,
) -> DashboardSnapshotRow:
    return DashboardSnapshotRow(
        asset_class=asset_class,
        segment=segment,
        name=f"ETF {isin}",
        isin=isin,
        invested_amount=current_value,
        units=current_value / price,
        missing_data=False,
        live_price=price,
        live_price_date=date(2026, 6, 8),
        live_price_source="Lang & Schwarz LSX",
        current_value=current_value,
        result_value=0,
        execution_count=1,
    )


def test_rebalance_plan_uses_saved_pac_real_budget_and_dashboard_snapshot():
    plan = calculate_rebalance_plan(
        snapshot(),
        simulation(),
        RebalanceMode.ONLY_UNDERWEIGHT,
    )

    rows_by_isin = {row.isin: row for row in plan.rows}
    operations_by_isin = {operation.isin: operation for operation in plan.operations}

    assert plan.budget == 102
    assert plan.total_current_value == 1_000
    assert plan.underweight_count == 2
    assert plan.overweight_count == 2
    assert rows_by_isin["AAA"].status == "Sottopesato"
    assert rows_by_isin["BBB"].status == "Sovrappesato"
    assert rows_by_isin["CCC"].status == "Sottopesato"
    assert rows_by_isin["DDD"].status == "Sovrappesato"
    assert rows_by_isin["EEE"].status == "Non calcolabile"
    assert rows_by_isin["BBB"].buy_amount == 0
    assert rows_by_isin["DDD"].buy_amount == 0
    assert rows_by_isin["EEE"].buy_amount == 0
    assert operations_by_isin["AAA"].buy_amount == 34
    assert operations_by_isin["CCC"].buy_amount == 68
    assert operations_by_isin["AAA"].estimated_units == 3.4
    assert operations_by_isin["CCC"].estimated_units == 13.6


def test_rebalance_plan_can_exclude_a_single_underweight_etf():
    plan = calculate_rebalance_plan(
        snapshot(),
        simulation(),
        RebalanceMode.ONLY_UNDERWEIGHT,
        overrides={"CCC": "exclude"},
    )

    rows_by_isin = {row.isin: row for row in plan.rows}

    assert rows_by_isin["AAA"].buy_amount == 102
    assert rows_by_isin["CCC"].buy_amount == 0
    assert rows_by_isin["CCC"].action == "Escludi"
    assert [operation.isin for operation in plan.operations] == ["AAA"]
