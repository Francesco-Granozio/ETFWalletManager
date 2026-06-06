from datetime import date

from app.domain import PortfolioPosition
from app.services.rebalance_service import RebalanceMode, calculate_rebalance


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
