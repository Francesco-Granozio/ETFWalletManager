from datetime import date

from sqlalchemy import text

from app.db.database import create_session_factory, init_database
from app.db.repositories import PortfolioRepository
from app.domain import (
    DashboardSnapshot,
    DashboardSnapshotRow,
    DEFAULT_PAC_EXECUTION_SCHEDULE,
    EtfMetadata,
    HistoricalPriceQuote,
    PacSimulationPreview,
    PacSimulationRow,
    PriceQuote,
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


def test_database_initializes_empty_portfolio_and_default_settings(tmp_path):
    db_path = tmp_path / "portfolio.db"
    session_factory = create_session_factory(db_path)
    init_database(session_factory)

    with session_factory() as session:
        repo = PortfolioRepository(session)

        assert repo.list_positions() == []
        assert repo.get_monthly_pac() == 0
        assert repo.settings_dict()["theme"] == "dark"
        assert repo.settings_dict()["auto_snapshot_enabled"] == "true"
        assert repo.settings_dict()["pac_execution_schedule"] == DEFAULT_PAC_EXECUTION_SCHEDULE


def test_repository_persists_etf_metadata_cache(tmp_path):
    db_path = tmp_path / "portfolio.db"
    session_factory = create_session_factory(db_path)
    init_database(session_factory)

    with session_factory() as session:
        repo = PortfolioRepository(session)
        repo.save_etf_metadata(metadata())
        session.commit()

    with session_factory() as session:
        repo = PortfolioRepository(session)
        cached = repo.get_etf_metadata("ie000xzsv718")

        assert cached == metadata()


def test_repository_clears_provider_price_and_metadata_cache_without_removing_portfolio(tmp_path):
    db_path = tmp_path / "portfolio.db"
    session_factory = create_session_factory(db_path)
    init_database(session_factory)
    preview = PacSimulationPreview(
        monthly_pac=100,
        round_up=False,
        real_monthly_pac=100,
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

    with session_factory() as session:
        repo = PortfolioRepository(session)
        repo.replace_portfolio_from_preview(preview)
        position = repo.list_positions()[0]
        repo.save_price(position.etf_id, price=15.71, price_date=date(2026, 6, 8), source="Lang & Schwarz LSX")
        session.commit()

    with session_factory() as session:
        repo = PortfolioRepository(session)
        result = repo.clear_provider_cache()
        session.commit()

    with session_factory() as session:
        repo = PortfolioRepository(session)
        positions = repo.list_positions()

        assert result == {
            "etf_prices": 1,
            "price_history": 2,
            "metadata_cache": 1,
        }
        assert len(positions) == 1
        assert positions[0].isin == "IE000XZSV718"
        assert positions[0].price == 0
        assert positions[0].price_date is None
        assert positions[0].price_source == "cache cleared"
        assert repo.find_price(positions[0].etf_id, date(2026, 6, 6)) is None
        assert repo.find_price(positions[0].etf_id, date(2026, 6, 8)) is None
        assert repo.get_etf_metadata("IE000XZSV718") is None


def test_repository_refreshes_saved_pac_and_execution_provider_data_without_recreating_rows(tmp_path):
    db_path = tmp_path / "portfolio.db"
    session_factory = create_session_factory(db_path)
    init_database(session_factory)
    preview = PacSimulationPreview(
        monthly_pac=100,
        round_up=False,
        real_monthly_pac=100,
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

    with session_factory() as session:
        repo = PortfolioRepository(session)
        simulation = repo.save_simulation_preview(preview, name="PAC LS")
        repo.replace_portfolio_from_preview(preview)
        execution = repo.save_pac_execution_from_simulation(
            simulation,
            execution_date=date(2026, 6, 2),
            quotes={
                "IE000XZSV718": HistoricalPriceQuote(
                    isin="IE000XZSV718",
                    price=14.56,
                    price_date=date(2026, 6, 2),
                    source="justETF chart",
                )
            },
        )
        repo.update_pac_execution_row_details(
            execution.rows[0].id,
            invested_amount=100,
            share_price=14.5,
            shares=6.896552,
        )
        session.commit()

    with session_factory() as session:
        repo = PortfolioRepository(session)
        assert repo.provider_refresh_isins() == ["IE000XZSV718"]

        result = repo.refresh_provider_data(
            {
                "IE000XZSV718": PriceQuote(
                    isin="IE000XZSV718",
                    price=15.71,
                    price_date=date(2026, 6, 8),
                    source="Lang & Schwarz LSX",
                    currency="EUR",
                    exchange="LSX",
                )
            }
        )
        session.commit()

    with session_factory() as session:
        repo = PortfolioRepository(session)
        position = repo.list_positions()[0]
        simulation = repo.list_simulations()[0]
        execution = repo.list_pac_executions()[0]
        row = execution.rows[0]
        cached = repo.get_etf_metadata("IE000XZSV718")

        assert result == {
            "etfs": 1,
            "simulation_rows": 1,
            "execution_rows": 1,
            "metadata_cache": 1,
            "price_history": 1,
        }
        assert position.price == 15.71
        assert position.price_source == "Lang & Schwarz LSX"
        assert position.exchange == "LSX"
        assert simulation.rows[0].metadata.price == 15.71
        assert simulation.rows[0].metadata.price_source == "Lang & Schwarz LSX"
        assert simulation.rows[0].metadata.exchange == "LSX"
        assert cached is not None
        assert cached.price == 15.71
        assert cached.price_source == "Lang & Schwarz LSX"
        assert row.current_price == 15.71
        assert row.current_price_source == "Lang & Schwarz LSX"
        assert row.share_price == 14.5
        assert row.shares == 6.896552
        assert row.previous_price is None
        assert row.price_diff is None
        assert row.price_diff_pct is None


def test_repository_saves_and_loads_latest_dashboard_snapshot(tmp_path):
    db_path = tmp_path / "portfolio.db"
    session_factory = create_session_factory(db_path)
    init_database(session_factory)

    first = DashboardSnapshot(
        total_invested=100,
        current_value=110,
        result_value=10,
        result_pct=0.10,
        latest_live_price_date=date(2026, 6, 8),
        execution_count=1,
        etf_count=1,
        quote_error_count=0,
        rows=[
            DashboardSnapshotRow(
                asset_class="Azioni",
                segment="S&P 500",
                name="ETF Azionario",
                isin="IE000XZSV718",
                invested_amount=100,
                units=10,
                missing_data=False,
                live_price=11,
                live_price_date=date(2026, 6, 8),
                live_price_source="Lang & Schwarz LSX",
                current_value=110,
                result_value=10,
                execution_count=1,
            )
        ],
    )
    second = DashboardSnapshot(
        total_invested=200,
        current_value=None,
        result_value=None,
        result_pct=None,
        latest_live_price_date=None,
        execution_count=2,
        etf_count=1,
        quote_error_count=1,
        rows=[
            DashboardSnapshotRow(
                asset_class="Azioni",
                segment="S&P 500",
                name="ETF Azionario",
                isin="IE000XZSV718",
                invested_amount=200,
                units=0,
                missing_data=True,
                live_price=None,
                live_price_date=None,
                live_price_source="",
                current_value=None,
                result_value=None,
                execution_count=2,
            )
        ],
    )

    with session_factory() as session:
        repo = PortfolioRepository(session)
        repo.save_dashboard_snapshot(first)
        repo.save_dashboard_snapshot(second)
        session.commit()

    with session_factory() as session:
        snapshot = PortfolioRepository(session).latest_dashboard_snapshot()

    assert snapshot is not None
    assert snapshot.id is not None
    assert snapshot.total_invested == 200
    assert snapshot.current_value is None
    assert snapshot.quote_error_count == 1
    assert len(snapshot.rows) == 1
    assert snapshot.rows[0].missing_data is True
    assert snapshot.rows[0].invested_amount == 200


def test_repository_replaces_portfolio_from_manual_pac_preview(tmp_path):
    db_path = tmp_path / "portfolio.db"
    session_factory = create_session_factory(db_path)
    init_database(session_factory)
    etf = metadata()
    preview = PacSimulationPreview(
        monthly_pac=100,
        round_up=False,
        real_monthly_pac=100,
        rows=[
            PacSimulationRow(
                asset_class="Azioni",
                asset_class_pct=1,
                segment_pct=1,
                target_pct=1,
                nominal_amount=100,
                effective_amount=100,
                metadata=etf,
            )
        ],
    )

    with session_factory() as session:
        repo = PortfolioRepository(session)
        repo.replace_portfolio_from_preview(preview)
        session.commit()

    with session_factory() as session:
        repo = PortfolioRepository(session)
        positions = repo.list_positions()

        assert repo.get_monthly_pac() == 100
        assert repo.settings_dict()["pac_execution_schedule"] == DEFAULT_PAC_EXECUTION_SCHEDULE
        assert len(positions) == 1
        assert positions[0].isin == "IE000XZSV718"
        assert positions[0].asset_class == "Azioni"
        assert positions[0].segment == "S&P 500"
        assert positions[0].target_pct == 1
        assert positions[0].target_segment_pct == 1
        assert positions[0].quantity == 0
        assert positions[0].price == 14.56
        assert repo.find_price(positions[0].etf_id, date(2026, 6, 6)) == 14.56


def test_repository_saves_and_lists_multiple_pac_simulations(tmp_path):
    db_path = tmp_path / "portfolio.db"
    session_factory = create_session_factory(db_path)
    init_database(session_factory)
    preview = PacSimulationPreview(
        monthly_pac=100,
        round_up=True,
        real_monthly_pac=101,
        rows=[
            PacSimulationRow(
                asset_class="Azioni",
                asset_class_pct=1,
                segment_pct=1,
                target_pct=1,
                nominal_amount=100,
                effective_amount=101,
                metadata=metadata(),
            )
        ],
    )

    with session_factory() as session:
        repo = PortfolioRepository(session)
        first = repo.save_simulation_preview(preview, name="Core")
        second = repo.save_simulation_preview(preview, name="Aggressiva")
        session.commit()

    with session_factory() as session:
        repo = PortfolioRepository(session)
        simulations = repo.list_simulations()

        assert [simulation.name for simulation in simulations] == ["Aggressiva", "Core"]
        assert {simulation.id for simulation in simulations} == {first.id, second.id}
        assert simulations[0].rows[0].metadata.isin == "IE000XZSV718"
        assert simulations[0].real_monthly_pac == 101
        assert simulations[0].execution_schedule == DEFAULT_PAC_EXECUTION_SCHEDULE


def test_database_migrates_existing_simulations_with_default_execution_schedule(tmp_path):
    db_path = tmp_path / "portfolio.db"
    session_factory = create_session_factory(db_path)
    engine = session_factory.kw["bind"]
    with engine.begin() as connection:
        connection.execute(
            text(
                """
                CREATE TABLE pac_simulations (
                    id INTEGER PRIMARY KEY,
                    name VARCHAR(120) NOT NULL,
                    monthly_pac FLOAT NOT NULL,
                    round_up BOOLEAN NOT NULL,
                    real_monthly_pac FLOAT NOT NULL,
                    created_at DATETIME NOT NULL,
                    updated_at DATETIME NOT NULL,
                    applied_at DATETIME
                )
                """
            )
        )

    init_database(session_factory)

    with engine.connect() as connection:
        columns = [row[1] for row in connection.execute(text("PRAGMA table_info(pac_simulations)"))]

    assert "execution_schedule" in columns


def test_database_migrates_existing_pac_execution_rows_with_broker_share_details(tmp_path):
    db_path = tmp_path / "portfolio.db"
    session_factory = create_session_factory(db_path)
    engine = session_factory.kw["bind"]
    with engine.begin() as connection:
        connection.execute(
            text(
                """
                CREATE TABLE pac_execution_rows (
                    id INTEGER PRIMARY KEY,
                    execution_id INTEGER NOT NULL,
                    sort_order INTEGER NOT NULL,
                    asset_class VARCHAR(80) NOT NULL,
                    segment VARCHAR(160) NOT NULL,
                    name VARCHAR(260) NOT NULL,
                    isin VARCHAR(12) NOT NULL,
                    invested_amount FLOAT NOT NULL,
                    currency VARCHAR(8) NOT NULL,
                    current_price FLOAT,
                    current_price_date DATE,
                    current_price_source VARCHAR(80) NOT NULL,
                    previous_price FLOAT,
                    price_diff FLOAT,
                    price_diff_pct FLOAT
                )
                """
            )
        )

    init_database(session_factory)

    with engine.connect() as connection:
        columns = [row[1] for row in connection.execute(text("PRAGMA table_info(pac_execution_rows)"))]

    assert "share_price" in columns
    assert "shares" in columns


def test_repository_deletes_saved_simulation_without_clearing_active_portfolio(tmp_path):
    db_path = tmp_path / "portfolio.db"
    session_factory = create_session_factory(db_path)
    init_database(session_factory)
    preview = PacSimulationPreview(
        monthly_pac=100,
        round_up=False,
        real_monthly_pac=100,
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

    with session_factory() as session:
        repo = PortfolioRepository(session)
        saved = repo.save_simulation_preview(preview, name="Da eliminare")
        repo.apply_saved_simulation(saved.id)
        repo.delete_simulation(saved.id)
        session.commit()

    with session_factory() as session:
        repo = PortfolioRepository(session)

        assert repo.list_simulations() == []
        assert len(repo.list_positions()) == 1
        assert repo.list_positions()[0].isin == "IE000XZSV718"


def test_repository_updates_manual_pac_execution_row_amount(tmp_path):
    db_path = tmp_path / "portfolio.db"
    session_factory = create_session_factory(db_path)
    init_database(session_factory)
    preview = PacSimulationPreview(
        monthly_pac=100,
        round_up=False,
        real_monthly_pac=100,
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

    with session_factory() as session:
        repo = PortfolioRepository(session)
        simulation = repo.save_simulation_preview(preview, name="PAC manuale")
        execution = repo.save_pac_execution_from_simulation(
            simulation,
            execution_date=date(2026, 2, 2),
            name="Febbraio",
            manual=True,
        )
        updated = repo.update_pac_execution_row_amount(execution.rows[0].id, 5000)
        session.commit()

    assert updated.rows[0].invested_amount == 5000
    assert updated.manual is True

    with session_factory() as session:
        executions = PortfolioRepository(session).list_pac_executions()

    assert executions[0].rows[0].invested_amount == 5000


def test_repository_updates_pac_execution_row_broker_share_details(tmp_path):
    db_path = tmp_path / "portfolio.db"
    session_factory = create_session_factory(db_path)
    init_database(session_factory)
    preview = PacSimulationPreview(
        monthly_pac=100,
        round_up=False,
        real_monthly_pac=100,
        rows=[
            PacSimulationRow(
                asset_class="Azioni",
                asset_class_pct=1,
                segment_pct=1,
                target_pct=1,
                nominal_amount=23,
                effective_amount=23,
                metadata=metadata(),
            )
        ],
    )

    with session_factory() as session:
        repo = PortfolioRepository(session)
        simulation = repo.save_simulation_preview(preview, name="PAC manuale")
        execution = repo.save_pac_execution_from_simulation(
            simulation,
            execution_date=date(2026, 2, 2),
            name="Febbraio",
            manual=False,
        )
        updated = repo.update_pac_execution_row_details(
            execution.rows[0].id,
            invested_amount=23,
            share_price=15.2445,
            shares=1.50874,
        )
        session.commit()

    assert updated.manual is True
    assert updated.rows[0].invested_amount == 23
    assert updated.rows[0].share_price == 15.2445
    assert updated.rows[0].shares == 1.50874
    assert updated.rows[0].has_share_details is True

    with session_factory() as session:
        row = PortfolioRepository(session).list_pac_executions()[0].rows[0]

    assert row.share_price == 15.2445
    assert row.shares == 1.50874


def test_init_database_imports_existing_active_portfolio_as_saved_simulation(tmp_path):
    db_path = tmp_path / "portfolio.db"
    session_factory = create_session_factory(db_path)
    init_database(session_factory)
    preview = PacSimulationPreview(
        monthly_pac=100,
        round_up=False,
        real_monthly_pac=100,
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

    with session_factory() as session:
        repo = PortfolioRepository(session)
        repo.replace_portfolio_from_preview(preview)
        session.commit()

    init_database(session_factory)

    with session_factory() as session:
        repo = PortfolioRepository(session)
        simulations = repo.list_simulations()

        assert len(simulations) == 1
        assert simulations[0].name == "PAC attivo importato"
        assert simulations[0].rows[0].metadata.isin == "IE000XZSV718"
