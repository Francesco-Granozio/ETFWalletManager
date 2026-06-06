from __future__ import annotations

from datetime import UTC, date, datetime

from sqlalchemy import Select, delete, func, select
from sqlalchemy.orm import Session

from app.domain import (
    EtfMetadata,
    PacSimulationPreview,
    PacSimulationRow,
    PortfolioPosition,
    PortfolioSnapshot,
    SavedPacSimulation,
)
from app.db.models import (
    EtfMetadataCacheModel,
    EtfModel,
    HoldingModel,
    PacSimulationModel,
    PacSimulationRowModel,
    PortfolioSnapshotModel,
    PriceHistoryModel,
    SettingModel,
)

DEFAULT_MONTHLY_PAC = 0.0
DEFAULT_SETTINGS = {
    "monthly_pac": str(DEFAULT_MONTHLY_PAC),
    "auto_update_enabled": "false",
    "auto_update_frequency": "daily",
    "auto_snapshot_enabled": "true",
    "theme": "dark",
    "rebalance_mode": "Compra ETF sottopesati",
    "fallback_price": "last_available",
}


class PortfolioRepository:
    def __init__(self, session: Session):
        self.session = session

    def has_etfs(self) -> bool:
        return bool(self.session.scalar(select(func.count(EtfModel.id))))

    def ensure_default_settings(self) -> None:
        for key, value in DEFAULT_SETTINGS.items():
            if self.get_setting(key) is None:
                self.set_setting(key, value)

    def ensure_simulation_from_active_portfolio(self) -> None:
        if self.session.scalar(select(func.count(PacSimulationModel.id))) or not self.has_etfs():
            return
        positions = self.list_positions()
        monthly_pac = self.get_monthly_pac()
        asset_totals: dict[str, float] = {}
        for position in positions:
            asset_totals[position.asset_class] = asset_totals.get(position.asset_class, 0) + position.target_pct

        rows: list[PacSimulationRow] = []
        for position in positions:
            asset_class_pct = asset_totals[position.asset_class]
            segment_pct = (
                position.target_segment_pct
                if position.target_segment_pct is not None
                else position.target_pct / asset_class_pct
                if asset_class_pct
                else 0
            )
            amount = round(monthly_pac * position.target_pct, 2)
            rows.append(
                PacSimulationRow(
                    asset_class=position.asset_class,
                    asset_class_pct=asset_class_pct,
                    segment_pct=segment_pct,
                    target_pct=position.target_pct,
                    nominal_amount=amount,
                    effective_amount=amount,
                    metadata=EtfMetadata(
                        isin=position.isin,
                        name=position.name,
                        segment=position.segment,
                        ticker=position.ticker,
                        exchange=position.exchange,
                        currency=position.currency,
                        ter=position.ter,
                        price=position.price,
                        price_date=position.price_date,
                        price_source=position.price_source,
                    ),
                )
            )
        self.save_simulation_preview(
            PacSimulationPreview(
                monthly_pac=monthly_pac,
                round_up=False,
                real_monthly_pac=monthly_pac,
                rows=rows,
            ),
            name="PAC attivo importato",
        )

    def list_positions(self) -> list[PortfolioPosition]:
        stmt = (
            select(EtfModel, HoldingModel)
            .join(HoldingModel, HoldingModel.etf_id == EtfModel.id, isouter=True)
            .where(EtfModel.enabled.is_(True))
            .order_by(EtfModel.asset_class.desc(), EtfModel.segment.asc())
        )
        return [self._to_position(etf, holding) for etf, holding in self.session.execute(stmt)]

    def save_holding(
        self,
        etf_id: int,
        quantity: float,
        average_price: float | None = None,
    ) -> None:
        holding = self.session.scalar(select(HoldingModel).where(HoldingModel.etf_id == etf_id))
        if not holding:
            holding = HoldingModel(etf_id=etf_id, quantity=0, average_price=0)
            self.session.add(holding)
        holding.quantity = float(quantity)
        if average_price is not None:
            holding.average_price = float(average_price)

    def save_price(
        self,
        etf_id: int,
        price: float,
        price_date: date,
        source: str,
    ) -> None:
        etf = self.session.get(EtfModel, etf_id)
        if not etf:
            raise ValueError(f"ETF not found: {etf_id}")
        etf.price = float(price)
        etf.price_date = price_date
        etf.price_source = source

        history = self.session.scalar(
            select(PriceHistoryModel).where(
                PriceHistoryModel.etf_id == etf_id,
                PriceHistoryModel.date == price_date,
            )
        )
        if not history:
            history = PriceHistoryModel(etf_id=etf_id, date=price_date, price=price, source=source)
            self.session.add(history)
        else:
            history.price = float(price)
            history.source = source

    def get_etf_metadata(self, isin: str) -> EtfMetadata | None:
        model = self.session.get(EtfMetadataCacheModel, _normalize_isin(isin))
        return self._to_etf_metadata(model) if model else None

    def save_etf_metadata(self, metadata: EtfMetadata) -> EtfMetadata:
        isin = _normalize_isin(metadata.isin)
        model = self.session.get(EtfMetadataCacheModel, isin)
        if not model:
            model = EtfMetadataCacheModel(isin=isin)
            self.session.add(model)
        model.name = metadata.name
        model.segment = metadata.segment
        model.ticker = metadata.ticker
        model.exchange = metadata.exchange
        model.currency = metadata.currency
        model.ter = float(metadata.ter)
        model.price = float(metadata.price)
        model.price_date = metadata.price_date
        model.price_source = metadata.price_source
        return EtfMetadata(
            isin=isin,
            name=model.name,
            segment=model.segment,
            ticker=model.ticker,
            exchange=model.exchange,
            currency=model.currency,
            ter=model.ter,
            price=model.price,
            price_date=model.price_date,
            price_source=model.price_source,
        )

    def clear_portfolio(self) -> None:
        self.session.execute(delete(PriceHistoryModel))
        self.session.execute(delete(HoldingModel))
        self.session.execute(delete(PortfolioSnapshotModel))
        self.session.execute(delete(EtfModel))

    def replace_portfolio_from_preview(self, preview: PacSimulationPreview) -> None:
        self.clear_portfolio()
        self.set_setting("monthly_pac", str(float(preview.monthly_pac)))
        for row in preview.rows:
            metadata = self.save_etf_metadata(row.metadata)
            etf = EtfModel(
                asset_class=row.asset_class,
                segment=metadata.segment,
                name=metadata.name,
                isin=metadata.isin,
                ticker=metadata.ticker,
                exchange=metadata.exchange,
                currency=metadata.currency,
                ter=metadata.ter,
                target_pct=row.target_pct,
                target_segment_pct=row.segment_pct,
                price=metadata.price,
                price_date=metadata.price_date,
                price_source=metadata.price_source,
                enabled=True,
            )
            self.session.add(etf)
            self.session.flush()
            self.session.add(
                HoldingModel(
                    etf_id=etf.id,
                    quantity=0,
                    average_price=metadata.price,
                )
            )
            if metadata.price > 0 and metadata.price_date is not None:
                self.session.add(
                    PriceHistoryModel(
                        etf_id=etf.id,
                        date=metadata.price_date,
                        price=metadata.price,
                        source=metadata.price_source,
                    )
                )

    def save_simulation_preview(
        self,
        preview: PacSimulationPreview,
        name: str | None = None,
        applied_at: datetime | None = None,
    ) -> SavedPacSimulation:
        model = PacSimulationModel(
            name=(name or "Simulazione PAC").strip() or "Simulazione PAC",
            monthly_pac=float(preview.monthly_pac),
            round_up=bool(preview.round_up),
            real_monthly_pac=float(preview.real_monthly_pac),
            applied_at=applied_at,
        )
        self.session.add(model)
        self.session.flush()

        for index, row in enumerate(preview.rows):
            metadata = self.save_etf_metadata(row.metadata)
            self.session.add(
                PacSimulationRowModel(
                    simulation_id=model.id,
                    sort_order=index,
                    asset_class=row.asset_class,
                    asset_class_pct=row.asset_class_pct,
                    segment_pct=row.segment_pct,
                    target_pct=row.target_pct,
                    nominal_amount=row.nominal_amount,
                    effective_amount=row.effective_amount,
                    isin=metadata.isin,
                    name=metadata.name,
                    segment=metadata.segment,
                    ticker=metadata.ticker,
                    exchange=metadata.exchange,
                    currency=metadata.currency,
                    ter=metadata.ter,
                    price=metadata.price,
                    price_date=metadata.price_date,
                    price_source=metadata.price_source,
                )
            )
        self.session.flush()
        return self._to_saved_simulation(model)

    def list_simulations(self) -> list[SavedPacSimulation]:
        models = self.session.scalars(
            select(PacSimulationModel).order_by(PacSimulationModel.id.desc())
        )
        return [self._to_saved_simulation(model) for model in models]

    def get_simulation(self, simulation_id: int) -> SavedPacSimulation | None:
        model = self.session.get(PacSimulationModel, simulation_id)
        return self._to_saved_simulation(model) if model else None

    def apply_saved_simulation(self, simulation_id: int) -> SavedPacSimulation:
        model = self.session.get(PacSimulationModel, simulation_id)
        if not model:
            raise ValueError(f"Simulation not found: {simulation_id}")
        saved = self._to_saved_simulation(model)
        self.replace_portfolio_from_preview(_preview_from_saved(saved))
        model.applied_at = datetime.now(UTC)
        return self._to_saved_simulation(model)

    def delete_simulation(self, simulation_id: int) -> None:
        model = self.session.get(PacSimulationModel, simulation_id)
        if not model:
            raise ValueError(f"Simulation not found: {simulation_id}")
        self.session.delete(model)

    def find_price(self, etf_id: int, target_date: date) -> float | None:
        exact = self._price_query(etf_id).where(PriceHistoryModel.date == target_date)
        price = self.session.scalar(exact)
        if price is not None:
            return float(price)

        after = (
            self._price_query(etf_id)
            .where(PriceHistoryModel.date > target_date)
            .order_by(PriceHistoryModel.date.asc())
            .limit(1)
        )
        price = self.session.scalar(after)
        if price is not None:
            return float(price)

        before = (
            self._price_query(etf_id)
            .where(PriceHistoryModel.date < target_date)
            .order_by(PriceHistoryModel.date.desc())
            .limit(1)
        )
        price = self.session.scalar(before)
        return float(price) if price is not None else None

    def get_snapshot(self, snapshot_date: date) -> PortfolioSnapshot | None:
        model = self.session.scalar(
            select(PortfolioSnapshotModel).where(PortfolioSnapshotModel.date == snapshot_date)
        )
        return self._to_snapshot(model) if model else None

    def save_snapshot(self, snapshot: PortfolioSnapshot) -> PortfolioSnapshot:
        model = self.session.scalar(
            select(PortfolioSnapshotModel).where(PortfolioSnapshotModel.date == snapshot.date)
        )
        if not model:
            model = PortfolioSnapshotModel(
                date=snapshot.date,
                total_value=snapshot.total_value,
                equity_value=snapshot.equity_value,
                bond_value=snapshot.bond_value,
                alternative_value=snapshot.alternative_value,
                monthly_diff=snapshot.monthly_diff,
                yearly_diff=snapshot.yearly_diff,
            )
            self.session.add(model)
        else:
            model.total_value = snapshot.total_value
            model.equity_value = snapshot.equity_value
            model.bond_value = snapshot.bond_value
            model.alternative_value = snapshot.alternative_value
            model.monthly_diff = snapshot.monthly_diff
            model.yearly_diff = snapshot.yearly_diff
        return snapshot

    def list_snapshots(self) -> list[PortfolioSnapshot]:
        models = self.session.scalars(select(PortfolioSnapshotModel).order_by(PortfolioSnapshotModel.date))
        return [self._to_snapshot(model) for model in models]

    def get_setting(self, key: str, default: str | None = None) -> str | None:
        setting = self.session.get(SettingModel, key)
        return setting.value if setting else default

    def set_setting(self, key: str, value: str) -> None:
        setting = self.session.get(SettingModel, key)
        if not setting:
            self.session.add(SettingModel(key=key, value=value))
        else:
            setting.value = value

    def get_monthly_pac(self) -> float:
        return float(self.get_setting("monthly_pac", str(DEFAULT_MONTHLY_PAC)) or DEFAULT_MONTHLY_PAC)

    def settings_dict(self) -> dict[str, str]:
        return {setting.key: setting.value for setting in self.session.scalars(select(SettingModel))}

    def _price_query(self, etf_id: int) -> Select[tuple[float]]:
        return select(PriceHistoryModel.price).where(PriceHistoryModel.etf_id == etf_id)

    @staticmethod
    def _to_position(etf: EtfModel, holding: HoldingModel | None) -> PortfolioPosition:
        return PortfolioPosition(
            etf_id=etf.id,
            asset_class=etf.asset_class,
            segment=etf.segment,
            name=etf.name,
            isin=etf.isin,
            ticker=etf.ticker,
            exchange=etf.exchange,
            currency=etf.currency,
            ter=etf.ter,
            target_pct=etf.target_pct,
            target_segment_pct=etf.target_segment_pct,
            quantity=holding.quantity if holding else 0,
            average_price=holding.average_price if holding else 0,
            price=etf.price,
            price_date=etf.price_date,
            price_source=etf.price_source,
            enabled=etf.enabled,
        )

    @staticmethod
    def _to_snapshot(model: PortfolioSnapshotModel) -> PortfolioSnapshot:
        return PortfolioSnapshot(
            date=model.date,
            total_value=model.total_value,
            equity_value=model.equity_value,
            bond_value=model.bond_value,
            alternative_value=model.alternative_value,
            monthly_diff=model.monthly_diff,
            yearly_diff=model.yearly_diff,
        )

    @staticmethod
    def _to_etf_metadata(model: EtfMetadataCacheModel) -> EtfMetadata:
        return EtfMetadata(
            isin=model.isin,
            name=model.name,
            segment=model.segment,
            ticker=model.ticker,
            exchange=model.exchange,
            currency=model.currency,
            ter=model.ter,
            price=model.price,
            price_date=model.price_date,
            price_source=model.price_source,
        )

    @staticmethod
    def _to_saved_simulation(model: PacSimulationModel) -> SavedPacSimulation:
        return SavedPacSimulation(
            id=model.id,
            name=model.name,
            monthly_pac=model.monthly_pac,
            round_up=model.round_up,
            real_monthly_pac=model.real_monthly_pac,
            created_at=model.created_at,
            updated_at=model.updated_at,
            applied_at=model.applied_at,
            rows=[_to_simulation_row(row) for row in model.rows],
        )


def _normalize_isin(isin: str) -> str:
    return isin.strip().upper()


def _to_simulation_row(model: PacSimulationRowModel) -> PacSimulationRow:
    return PacSimulationRow(
        asset_class=model.asset_class,
        asset_class_pct=model.asset_class_pct,
        segment_pct=model.segment_pct,
        target_pct=model.target_pct,
        nominal_amount=model.nominal_amount,
        effective_amount=model.effective_amount,
        metadata=EtfMetadata(
            isin=model.isin,
            name=model.name,
            segment=model.segment,
            ticker=model.ticker,
            exchange=model.exchange,
            currency=model.currency,
            ter=model.ter,
            price=model.price,
            price_date=model.price_date,
            price_source=model.price_source,
        ),
    )


def _preview_from_saved(simulation: SavedPacSimulation) -> PacSimulationPreview:
    return PacSimulationPreview(
        monthly_pac=simulation.monthly_pac,
        round_up=simulation.round_up,
        real_monthly_pac=simulation.real_monthly_pac,
        rows=simulation.rows,
    )
