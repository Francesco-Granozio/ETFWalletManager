from __future__ import annotations

from contextlib import contextmanager
from datetime import UTC, date, datetime
from typing import Iterator

from sqlalchemy.orm import Session, sessionmaker

from app.db.repositories import PortfolioRepository
from app.domain import (
    AllocationSummary,
    EtfMetadata,
    PacEtfAllocation,
    PacSimulationPreview,
    PerformanceReport,
    PortfolioPosition,
    PortfolioSnapshot,
    RebalanceRow,
    SavedPacSimulation,
)
from app.services.etf_metadata_service import EtfMetadataProvider, EtfMetadataService, normalize_isin
from app.services.performance_service import PerformanceService
from app.services.pac_simulation_service import calculate_pac_simulation
from app.services.portfolio_service import calculate_allocation
from app.services.price_service import PriceProvider, PriceService
from app.services.rebalance_service import RebalanceMode, calculate_rebalance


class AppContext:
    def __init__(self, session_factory: sessionmaker[Session]):
        self.session_factory = session_factory

    def positions(self) -> list[PortfolioPosition]:
        with self._repo() as repo:
            return repo.list_positions()

    def monthly_pac(self) -> float:
        with self._repo() as repo:
            return repo.get_monthly_pac()

    def allocation_summary(self) -> AllocationSummary:
        with self._repo() as repo:
            return calculate_allocation(repo.list_positions(), repo.get_monthly_pac())

    def rebalance_rows(
        self,
        monthly_pac: float | None = None,
        mode: RebalanceMode | str = RebalanceMode.ONLY_UNDERWEIGHT,
    ) -> list[RebalanceRow]:
        with self._repo() as repo:
            selected_pac = repo.get_monthly_pac() if monthly_pac is None else monthly_pac
            selected_mode = RebalanceMode(mode)
            return calculate_rebalance(repo.list_positions(), selected_pac, selected_mode)

    def performance_report(self, today: date | None = None) -> PerformanceReport:
        with self._repo() as repo:
            return PerformanceService(repo).build_report(today or date.today())

    def snapshots(self) -> list[PortfolioSnapshot]:
        with self._repo() as repo:
            return repo.list_snapshots()

    def create_current_month_snapshot(self, today: date | None = None) -> PortfolioSnapshot:
        snapshot_today = today or date.today()
        with self._session() as session:
            repo = PortfolioRepository(session)
            service = PerformanceService(repo)
            positions = repo.list_positions()

            def lookup(position: PortfolioPosition, snapshot_date: date) -> float:
                return repo.find_price(position.etf_id, snapshot_date) or position.price

            snapshot = service.ensure_current_month_snapshot(snapshot_today, positions, lookup)
            session.commit()
            return snapshot

    def save_holding(
        self,
        etf_id: int,
        quantity: float,
        average_price: float | None = None,
    ) -> None:
        with self._session() as session:
            PortfolioRepository(session).save_holding(etf_id, quantity, average_price)
            session.commit()

    def save_manual_price(self, etf_id: int, price: float, price_date: date | None = None) -> None:
        with self._session() as session:
            PortfolioRepository(session).save_price(
                etf_id,
                price=price,
                price_date=price_date or date.today(),
                source="manual",
            )
            session.commit()

    def resolve_etf_metadata(
        self,
        isin: str,
        force_refresh: bool = False,
        metadata_provider: EtfMetadataProvider | None = None,
    ) -> EtfMetadata:
        with self._session() as session:
            repo = PortfolioRepository(session)
            metadata = EtfMetadataService(metadata_provider).resolve(repo, isin, force_refresh)
            session.commit()
            return metadata

    def simulate_pac(
        self,
        monthly_pac: float,
        asset_allocations: dict[str, float],
        etf_allocations: list[PacEtfAllocation],
        round_up: bool = False,
        force_refresh: bool = False,
        metadata_provider: EtfMetadataProvider | None = None,
    ) -> PacSimulationPreview:
        metadata_by_isin: dict[str, EtfMetadata] = {}
        with self._session() as session:
            repo = PortfolioRepository(session)
            metadata_service = EtfMetadataService(metadata_provider)
            for allocation in etf_allocations:
                isin = normalize_isin(allocation.isin)
                if isin not in metadata_by_isin:
                    metadata_by_isin[isin] = metadata_service.resolve(repo, isin, force_refresh)
            session.commit()
        return calculate_pac_simulation(
            monthly_pac=monthly_pac,
            asset_allocations=asset_allocations,
            etf_allocations=etf_allocations,
            metadata_by_isin=metadata_by_isin,
            round_up=round_up,
        )

    def save_simulation_preview(
        self,
        preview: PacSimulationPreview,
        name: str | None = None,
    ) -> SavedPacSimulation:
        with self._session() as session:
            saved = PortfolioRepository(session).save_simulation_preview(preview, name)
            session.commit()
            return saved

    def saved_pac_simulations(self) -> list[SavedPacSimulation]:
        with self._repo() as repo:
            return repo.list_simulations()

    def apply_saved_simulation(self, simulation_id: int) -> SavedPacSimulation:
        with self._session() as session:
            saved = PortfolioRepository(session).apply_saved_simulation(simulation_id)
            session.commit()
            return saved

    def delete_saved_simulation(self, simulation_id: int) -> None:
        with self._session() as session:
            PortfolioRepository(session).delete_simulation(simulation_id)
            session.commit()

    def save_pac_simulation(
        self,
        preview: PacSimulationPreview,
        name: str | None = None,
    ) -> SavedPacSimulation:
        with self._session() as session:
            repo = PortfolioRepository(session)
            saved = repo.save_simulation_preview(preview, name, applied_at=datetime.now(UTC))
            repo.replace_portfolio_from_preview(preview)
            session.commit()
            return saved

    def update_prices(self, provider: PriceProvider | None = None):
        with self._session() as session:
            repo = PortfolioRepository(session)
            results = PriceService(provider).update_current_prices(repo)
            session.commit()
            return results

    def settings(self) -> dict[str, str]:
        with self._repo() as repo:
            return repo.settings_dict()

    def save_settings(self, values: dict[str, str]) -> None:
        with self._session() as session:
            repo = PortfolioRepository(session)
            for key, value in values.items():
                repo.set_setting(key, value)
            session.commit()

    @contextmanager
    def _session(self) -> Iterator[Session]:
        with self.session_factory() as session:
            yield session

    @contextmanager
    def _repo(self) -> Iterator[PortfolioRepository]:
        with self.session_factory() as session:
            yield PortfolioRepository(session)
