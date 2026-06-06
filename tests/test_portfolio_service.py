from datetime import date

from app.domain import PortfolioPosition
from app.services.portfolio_service import calculate_allocation


def position(
    isin: str,
    asset_class: str,
    target_pct: float,
    quantity: float,
    price: float,
    ter: float = 0.001,
) -> PortfolioPosition:
    return PortfolioPosition(
        etf_id=1,
        asset_class=asset_class,
        segment="Segment",
        name=isin,
        isin=isin,
        ticker=None,
        exchange="GETTEX",
        currency="EUR",
        ter=ter,
        target_pct=target_pct,
        target_segment_pct=None,
        quantity=quantity,
        average_price=price,
        price=price,
        price_date=date(2026, 6, 6),
        price_source="manual",
        enabled=True,
    )


def test_allocation_calculates_weights_drifts_and_asset_summary():
    positions = [
        position("AAA", "Azioni", 0.60, 6, 100, 0.002),
        position("BBB", "Obbligazioni", 0.40, 8, 50, 0.001),
    ]

    summary = calculate_allocation(positions, monthly_pac=204)

    assert summary.total_value == 1000
    assert round(summary.weighted_ter, 4) == 0.0016
    assert summary.rows[0].current_value == 600
    assert summary.rows[0].current_weight == 0.60
    assert summary.rows[0].target_value == 600
    assert summary.rows[0].monthly_pac_amount == 122.4
    assert summary.asset_classes["Azioni"].value == 600
    assert summary.asset_classes["Obbligazioni"].target_pct == 0.40


def test_allocation_handles_empty_or_zero_value_portfolio():
    summary = calculate_allocation([], monthly_pac=204)

    assert summary.total_value == 0
    assert summary.weighted_ter == 0
    assert summary.rows == []
    assert summary.asset_classes == {}
