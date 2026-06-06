from datetime import UTC, date, datetime

import pytest

from app.db.database import create_session_factory, init_database
from app.db.repositories import PortfolioRepository
from app.domain import (
    DEFAULT_PAC_EXECUTION_SCHEDULE,
    EtfMetadata,
    HistoricalPriceQuote,
    PacSimulationPreview,
    PacSimulationRow,
)
from app.services.pac_execution_service import (
    PacExecutionService,
    default_execution_name,
    schedule_due_dates,
)


def metadata(isin: str = "IE000XZSV718") -> EtfMetadata:
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


def preview(schedule: str = DEFAULT_PAC_EXECUTION_SCHEDULE) -> PacSimulationPreview:
    return PacSimulationPreview(
        monthly_pac=100,
        round_up=False,
        real_monthly_pac=100,
        execution_schedule=schedule,
        rows=[
            PacSimulationRow(
                asset_class="Azioni",
                asset_class_pct=1,
                segment_pct=1,
                target_pct=1,
                nominal_amount=100,
                effective_amount=100,
                metadata=metadata(),
            )
        ],
    )


class FakeHistoricalPriceProvider:
    def __init__(self, prices: dict[tuple[str, date], float]):
        self.prices = prices
        self.calls: list[tuple[str, date]] = []

    def fetch(self, isin: str, target_date: date, currency: str = "EUR") -> HistoricalPriceQuote:
        self.calls.append((isin, target_date))
        return HistoricalPriceQuote(
            isin=isin,
            price=self.prices[(isin, target_date)],
            price_date=target_date,
            source="fake justETF",
            currency=currency,
        )


def test_schedule_due_dates_supports_configured_frequencies():
    assert schedule_due_dates(
        "Settimanale dal 2 del mese",
        active_from=date(2026, 6, 1),
        today=date(2026, 6, 20),
    ) == [date(2026, 6, 2), date(2026, 6, 9), date(2026, 6, 16)]
    assert schedule_due_dates(
        "2 volte al mese dal 16 del mese",
        active_from=date(2026, 6, 1),
        today=date(2026, 7, 3),
    ) == [date(2026, 6, 16), date(2026, 7, 2)]
    assert schedule_due_dates(
        "Mensile dal 2 del mese",
        active_from=date(2026, 5, 20),
        today=date(2026, 6, 10),
    ) == [date(2026, 6, 2)]
    assert schedule_due_dates(
        "Ogni 3 mesi dal 16 del mese",
        active_from=date(2026, 6, 1),
        today=date(2026, 10, 1),
    ) == [date(2026, 6, 16), date(2026, 9, 16)]


def test_default_execution_names_match_frequency():
    assert (
        default_execution_name("Settimanale dal 2 del mese", date(2026, 6, 9))
        == "Esecuzione Settimana 2 inizio 9 Giugno"
    )
    assert (
        default_execution_name("2 volte al mese dal 16 del mese", date(2026, 7, 2))
        == "Esecuzione Mensile 2 inizio 2 Luglio"
    )
    assert (
        default_execution_name("Mensile dal 2 del mese", date(2026, 6, 2))
        == "Esecuzione mensile inizio 2 Giugno"
    )
    assert (
        default_execution_name("Ogni 3 mesi dal 2 del mese", date(2026, 6, 2))
        == "Esecuzione trimestrale inizio 2 Giugno"
    )


def test_pac_execution_service_creates_due_executions_with_price_diff(tmp_path):
    db_path = tmp_path / "portfolio.db"
    session_factory = create_session_factory(db_path)
    init_database(session_factory)
    provider = FakeHistoricalPriceProvider(
        {
            ("IE000XZSV718", date(2026, 5, 2)): 10,
            ("IE000XZSV718", date(2026, 6, 2)): 12,
        }
    )

    with session_factory() as session:
        repo = PortfolioRepository(session)
        repo.save_simulation_preview(
            preview("Mensile dal 2 del mese"),
            name="PAC attivo",
            applied_at=datetime(2026, 5, 1, tzinfo=UTC),
        )
        service = PacExecutionService(provider)

        created = service.ensure_due_executions(repo, today=date(2026, 6, 10))
        session.commit()

    assert [execution.execution_date for execution in created] == [
        date(2026, 5, 2),
        date(2026, 6, 2),
    ]

    with session_factory() as session:
        executions = PortfolioRepository(session).list_pac_executions()

    latest = executions[0]
    assert latest.execution_date == date(2026, 6, 2)
    assert latest.rows[0].invested_amount == pytest.approx(100)
    assert latest.rows[0].current_price == pytest.approx(12)
    assert latest.rows[0].previous_price == pytest.approx(10)
    assert latest.rows[0].price_diff == pytest.approx(2)
    assert latest.rows[0].price_diff_pct == pytest.approx(0.2)
