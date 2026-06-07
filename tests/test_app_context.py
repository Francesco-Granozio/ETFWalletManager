from datetime import date

from app.app_context import AppContext
from app.db.database import create_session_factory, init_database
from app.domain import (
    DEFAULT_PAC_EXECUTION_SCHEDULE,
    EtfMetadata,
    HistoricalPriceQuote,
    PacEtfAllocation,
    PriceQuote,
)
from app.services.dashboard_service import build_dashboard_summary
from app.services.rebalance_service import RebalanceMode


def make_context(tmp_path):
    session_factory = create_session_factory(tmp_path / "portfolio.db")
    init_database(session_factory)
    return AppContext(session_factory)


def metadata(isin: str) -> EtfMetadata:
    return EtfMetadata(
        isin=isin,
        name="SPDR S&P 500 UCITS ETF (Acc)",
        segment="S&P 500",
        ticker="SPYL",
        exchange="GETTEX",
        currency="EUR",
        ter=0.0003,
        price=14.56,
        price_date=date(2026, 6, 6),
        price_source="justETF",
    )


class FakeMetadataProvider:
    def __init__(self):
        self.calls: list[str] = []

    def fetch(self, isin: str) -> EtfMetadata:
        self.calls.append(isin)
        return metadata(isin)


class FakePriceProvider:
    def fetch(self, isin: str) -> PriceQuote:
        if isin == "IE000FAIL001":
            raise TimeoutError("timeout")
        return PriceQuote(
            isin=isin,
            price=12.34,
            price_date=date(2026, 6, 8),
            source="fake justETF",
        )


class FakeLsPriceProvider:
    def fetch(self, isin: str) -> PriceQuote:
        return PriceQuote(
            isin=isin,
            price=15.71,
            price_date=date(2026, 6, 8),
            source="Lang & Schwarz LSX",
            currency="EUR",
            exchange="LSX",
        )


class FakeHistoricalPriceProvider:
    def fetch(self, isin: str, target_date: date, currency: str = "EUR") -> HistoricalPriceQuote:
        return HistoricalPriceQuote(
            isin=isin,
            price=14.56,
            price_date=target_date,
            source="justETF chart",
            currency=currency,
        )


def test_app_context_starts_from_empty_allocation_and_snapshot(tmp_path):
    context = make_context(tmp_path)

    allocation = context.allocation_summary()
    snapshot = context.create_current_month_snapshot(date(2026, 6, 10))

    assert allocation.total_value == 0
    assert allocation.rows == []
    assert context.monthly_pac() == 0
    assert snapshot.date == date(2026, 6, 1)
    assert snapshot.total_value == 0


def test_app_context_simulates_and_persists_manual_pac(tmp_path):
    context = make_context(tmp_path)
    provider = FakeMetadataProvider()

    preview = context.simulate_pac(
        monthly_pac=100,
        asset_allocations={
            "Azioni": 1,
            "Obbligazioni": 0,
            "Alternativi": 0,
        },
        etf_allocations=[PacEtfAllocation("Azioni", "IE000XZSV718", 1)],
        round_up=False,
        metadata_provider=provider,
    )
    context.save_pac_simulation(preview)

    positions = context.positions()
    assert provider.calls == ["IE000XZSV718"]
    assert context.monthly_pac() == 100
    assert len(positions) == 1
    assert positions[0].isin == "IE000XZSV718"
    assert positions[0].target_pct == 1
    simulations = context.saved_pac_simulations()
    assert [simulation.name for simulation in simulations] == ["Simulazione PAC"]
    assert simulations[0].execution_schedule == DEFAULT_PAC_EXECUTION_SCHEDULE


def test_app_context_saves_multiple_simulations_and_applies_selected_one(tmp_path):
    context = make_context(tmp_path)
    provider = FakeMetadataProvider()

    first = context.simulate_pac(
        monthly_pac=100,
        asset_allocations={
            "Azioni": 1,
            "Obbligazioni": 0,
            "Alternativi": 0,
        },
        etf_allocations=[PacEtfAllocation("Azioni", "IE000XZSV718", 1)],
        metadata_provider=provider,
    )
    second = context.simulate_pac(
        monthly_pac=250,
        asset_allocations={
            "Azioni": 1,
            "Obbligazioni": 0,
            "Alternativi": 0,
        },
        etf_allocations=[PacEtfAllocation("Azioni", "IE000XZSV718", 1)],
        metadata_provider=provider,
    )

    saved_first = context.save_simulation_preview(first, "Prima")
    saved_second = context.save_simulation_preview(second, "Seconda")
    context.apply_saved_simulation(saved_second.id)

    assert [simulation.name for simulation in context.saved_pac_simulations()] == ["Seconda", "Prima"]
    assert saved_first.id != saved_second.id
    assert context.monthly_pac() == 250
    assert context.settings()["pac_execution_schedule"] == DEFAULT_PAC_EXECUTION_SCHEDULE


def test_app_context_deletes_selected_saved_simulation(tmp_path):
    context = make_context(tmp_path)
    provider = FakeMetadataProvider()
    preview = context.simulate_pac(
        monthly_pac=100,
        asset_allocations={
            "Azioni": 1,
            "Obbligazioni": 0,
            "Alternativi": 0,
        },
        etf_allocations=[PacEtfAllocation("Azioni", "IE000XZSV718", 1)],
        metadata_provider=provider,
    )
    saved = context.save_simulation_preview(preview, "Temporanea")

    context.delete_saved_simulation(saved.id)

    assert context.saved_pac_simulations() == []


def test_app_context_fetches_live_price_quotes_for_dashboard(tmp_path):
    context = make_context(tmp_path)

    quotes, errors = context.live_price_quotes(
        ["ie000xzsv718", "IE000FAIL001"],
        price_provider=FakePriceProvider(),
    )

    assert quotes["IE000XZSV718"].price == 12.34
    assert quotes["IE000XZSV718"].source == "fake justETF"
    assert "timeout" in errors["IE000FAIL001"]


def test_app_context_persists_dashboard_snapshot_and_builds_rebalance_plan(tmp_path):
    context = make_context(tmp_path)
    provider = FakeMetadataProvider()
    preview = context.simulate_pac(
        monthly_pac=100,
        asset_allocations={
            "Azioni": 1,
            "Obbligazioni": 0,
            "Alternativi": 0,
        },
        etf_allocations=[PacEtfAllocation("Azioni", "IE000XZSV718", 1)],
        metadata_provider=provider,
    )
    saved = context.save_simulation_preview(preview, "PAC target")
    execution = context.create_manual_pac_execution(
        saved.id,
        date(2026, 6, 2),
        price_provider=FakeHistoricalPriceProvider(),
    )
    context.update_pac_execution_row_details(
        execution.rows[0].id,
        invested_amount=50,
        share_price=10,
        shares=5,
    )
    summary = build_dashboard_summary(
        context.pac_executions(),
        {
            "IE000XZSV718": PriceQuote(
                isin="IE000XZSV718",
                price=10,
                price_date=date(2026, 6, 8),
                source="Lang & Schwarz LSX",
            )
        },
    )

    context.save_dashboard_snapshot(summary, {})
    snapshot = context.latest_dashboard_snapshot()
    plan = context.rebalance_plan_for_simulation(saved.id, RebalanceMode.ONLY_UNDERWEIGHT)

    assert snapshot is not None
    assert snapshot.current_value == 50
    assert plan.simulation_id == saved.id
    assert plan.budget == 100
    assert plan.rows[0].isin == "IE000XZSV718"
    assert plan.rows[0].buy_amount == 100


def test_app_context_clears_provider_cache(tmp_path):
    context = make_context(tmp_path)
    provider = FakeMetadataProvider()
    preview = context.simulate_pac(
        monthly_pac=100,
        asset_allocations={
            "Azioni": 1,
            "Obbligazioni": 0,
            "Alternativi": 0,
        },
        etf_allocations=[PacEtfAllocation("Azioni", "IE000XZSV718", 1)],
        metadata_provider=provider,
    )
    context.save_pac_simulation(preview)

    result = context.clear_provider_cache()

    assert result["etf_prices"] == 1
    assert result["price_history"] == 1
    assert result["metadata_cache"] == 1
    assert context.positions()[0].price == 0


def test_app_context_refreshes_provider_data_for_existing_pacs(tmp_path):
    context = make_context(tmp_path)
    provider = FakeMetadataProvider()
    preview = context.simulate_pac(
        monthly_pac=100,
        asset_allocations={
            "Azioni": 1,
            "Obbligazioni": 0,
            "Alternativi": 0,
        },
        etf_allocations=[PacEtfAllocation("Azioni", "IE000XZSV718", 1)],
        metadata_provider=provider,
    )
    saved = context.save_simulation_preview(preview, "PAC da aggiornare")
    context.apply_saved_simulation(saved.id)
    context.create_manual_pac_execution(
        saved.id,
        date(2026, 6, 2),
        price_provider=FakeHistoricalPriceProvider(),
    )

    result = context.refresh_provider_data(price_provider=FakeLsPriceProvider())

    assert result["isins"] == 1
    assert result["updated"]["etfs"] == 1
    assert result["updated"]["simulation_rows"] == 1
    assert result["updated"]["execution_rows"] == 1
    assert result["errors"] == {}
    assert context.positions()[0].price == 15.71
    assert context.saved_pac_simulations()[0].rows[0].metadata.price_source == "Lang & Schwarz LSX"
    assert context.pac_executions()[0].rows[0].current_price_source == "Lang & Schwarz LSX"
