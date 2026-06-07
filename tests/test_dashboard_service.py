from datetime import UTC, date, datetime

from app.domain import PacExecution, PacExecutionRow, PriceQuote
from app.services.dashboard_service import build_dashboard_summary, dashboard_snapshot_from_summary


def test_dashboard_snapshot_from_summary_keeps_calculable_and_missing_rows():
    execution = PacExecution(
        id=1,
        simulation_id=1,
        simulation_name="PAC attivo",
        execution_schedule="Mensile dal 2 del mese",
        name="Giugno",
        execution_date=datetime(2026, 6, 2, tzinfo=UTC).date(),
        manual=False,
        created_at=datetime(2026, 6, 2, tzinfo=UTC),
        updated_at=datetime(2026, 6, 2, tzinfo=UTC),
        rows=[
            PacExecutionRow(
                id=10,
                asset_class="Azioni",
                segment="S&P 500",
                name="ETF Azionario",
                isin="IE000XZSV718",
                invested_amount=100,
                currency="EUR",
                share_price=10,
                shares=10,
            ),
            PacExecutionRow(
                id=11,
                asset_class="Obbligazioni",
                segment="Gov Bond",
                name="ETF Bond",
                isin="IE000BOND001",
                invested_amount=50,
                currency="EUR",
            ),
        ],
    )
    summary = build_dashboard_summary(
        [execution],
        live_quotes={
            "IE000XZSV718": PriceQuote(
                isin="IE000XZSV718",
                price=12,
                price_date=date(2026, 6, 8),
                source="Lang & Schwarz LSX",
            )
        },
    )

    snapshot = dashboard_snapshot_from_summary(summary, {"IE000BOND001": "timeout"})

    assert snapshot.total_invested == 150
    assert snapshot.current_value is None
    assert snapshot.result_value is None
    assert snapshot.latest_live_price_date == date(2026, 6, 8)
    assert snapshot.quote_error_count == 1
    assert len(snapshot.rows) == 2
    assert snapshot.rows[0].isin == "IE000XZSV718"
    assert snapshot.rows[0].current_value == 120
    assert snapshot.rows[0].missing_data is False
    assert snapshot.rows[1].isin == "IE000BOND001"
    assert snapshot.rows[1].current_value is None
    assert snapshot.rows[1].missing_data is True
