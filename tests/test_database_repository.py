from datetime import date

from app.db.database import create_session_factory, init_database
from app.db.repositories import PortfolioRepository
from app.domain import EtfMetadata, PacSimulationPreview, PacSimulationRow


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
