from datetime import date

from app.app_context import AppContext
from app.db.database import create_session_factory, init_database
from app.domain import DEFAULT_PAC_EXECUTION_SCHEDULE, EtfMetadata, PacEtfAllocation


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
