from __future__ import annotations

from datetime import UTC, date, datetime

from sqlalchemy import Select, delete, func, select
from sqlalchemy.orm import Session

from app.domain import (
    DashboardSnapshot,
    DashboardSnapshotRow,
    DEFAULT_PAC_EXECUTION_SCHEDULE,
    EtfMetadata,
    HistoricalPriceQuote,
    PacExecution,
    PacExecutionRow,
    PacSimulationPreview,
    PacSimulationRow,
    PortfolioPosition,
    PortfolioSnapshot,
    PriceQuote,
    SavedPacSimulation,
)
from app.db.models import (
    DashboardSnapshotModel,
    DashboardSnapshotRowModel,
    EtfMetadataCacheModel,
    EtfModel,
    HoldingModel,
    PacExecutionModel,
    PacExecutionRowModel,
    PacSimulationModel,
    PacSimulationRowModel,
    PortfolioSnapshotModel,
    PriceHistoryModel,
    SettingModel,
)

DEFAULT_MONTHLY_PAC = 0.0
DEFAULT_SETTINGS = {
    "monthly_pac": str(DEFAULT_MONTHLY_PAC),
    "pac_execution_schedule": DEFAULT_PAC_EXECUTION_SCHEDULE,
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
                execution_schedule=self.get_setting("pac_execution_schedule", DEFAULT_PAC_EXECUTION_SCHEDULE)
                or DEFAULT_PAC_EXECUTION_SCHEDULE,
            ),
            name="PAC attivo importato",
            applied_at=datetime.now(UTC),
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

    def _upsert_price_history(self, etf_id: int, quote: PriceQuote) -> None:
        history = self.session.scalar(
            select(PriceHistoryModel).where(
                PriceHistoryModel.etf_id == etf_id,
                PriceHistoryModel.date == quote.price_date,
            )
        )
        if not history:
            history = PriceHistoryModel(
                etf_id=etf_id,
                date=quote.price_date,
                price=quote.price,
                source=quote.source,
            )
            self.session.add(history)
            return
        history.price = float(quote.price)
        history.source = quote.source

    def clear_provider_cache(self) -> dict[str, int]:
        etf_price_count = self.session.scalar(select(func.count(EtfModel.id))) or 0
        price_history_result = self.session.execute(delete(PriceHistoryModel))
        metadata_result = self.session.execute(delete(EtfMetadataCacheModel))
        for etf in self.session.scalars(select(EtfModel)):
            etf.price = 0
            etf.price_date = None
            etf.price_source = "cache cleared"
        return {
            "etf_prices": int(etf_price_count),
            "price_history": int(price_history_result.rowcount or 0),
            "metadata_cache": int(metadata_result.rowcount or 0),
        }

    def provider_refresh_isins(self) -> list[str]:
        isins: set[str] = set()
        for model in (EtfModel, PacSimulationRowModel, PacExecutionRowModel, EtfMetadataCacheModel):
            isins.update(
                _normalize_isin(isin)
                for isin in self.session.scalars(select(model.isin))
                if isin and isin.strip()
            )
        return sorted(isins)

    def refresh_provider_data(self, quotes: dict[str, PriceQuote]) -> dict[str, int]:
        quotes_by_isin = {
            _normalize_isin(isin): quote
            for isin, quote in quotes.items()
            if isin and quote is not None
        }
        result = {
            "etfs": 0,
            "simulation_rows": 0,
            "execution_rows": 0,
            "metadata_cache": 0,
            "price_history": 0,
        }
        if not quotes_by_isin:
            return result

        for etf in self.session.scalars(select(EtfModel)):
            quote = quotes_by_isin.get(_normalize_isin(etf.isin))
            if quote is None:
                continue
            _apply_quote_to_price_fields(etf, quote)
            self._upsert_price_history(etf.id, quote)
            result["etfs"] += 1
            result["price_history"] += 1

        for row in self.session.scalars(select(PacSimulationRowModel)):
            quote = quotes_by_isin.get(_normalize_isin(row.isin))
            if quote is None:
                continue
            _apply_quote_to_price_fields(row, quote)
            result["simulation_rows"] += 1

        for row in self.session.scalars(select(PacExecutionRowModel)):
            quote = quotes_by_isin.get(_normalize_isin(row.isin))
            if quote is None:
                continue
            row.current_price = float(quote.price)
            row.current_price_date = quote.price_date
            row.current_price_source = quote.source
            row.currency = quote.currency or row.currency
            row.previous_price = None
            row.price_diff = None
            row.price_diff_pct = None
            result["execution_rows"] += 1

        for cached in self.session.scalars(select(EtfMetadataCacheModel)):
            quote = quotes_by_isin.get(_normalize_isin(cached.isin))
            if quote is None:
                continue
            _apply_quote_to_price_fields(cached, quote)
            result["metadata_cache"] += 1

        return result

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
        self.set_setting("pac_execution_schedule", preview.execution_schedule)
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
            execution_schedule=preview.execution_schedule,
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

    def get_active_simulation(self) -> SavedPacSimulation | None:
        model = self.session.scalars(
            select(PacSimulationModel)
            .where(PacSimulationModel.applied_at.is_not(None))
            .order_by(PacSimulationModel.applied_at.desc(), PacSimulationModel.id.desc())
            .limit(1)
        ).first()
        return self._to_saved_simulation(model) if model else None

    def list_pac_executions(self) -> list[PacExecution]:
        models = self.session.scalars(
            select(PacExecutionModel).order_by(
                PacExecutionModel.execution_date.desc(),
                PacExecutionModel.id.desc(),
            )
        )
        return [self._to_pac_execution(model) for model in models]

    def get_pac_execution(self, execution_id: int) -> PacExecution | None:
        model = self.session.get(PacExecutionModel, execution_id)
        return self._to_pac_execution(model) if model else None

    def latest_pac_execution(
        self,
        simulation_id: int,
        before: date | None = None,
    ) -> PacExecution | None:
        model = self._latest_pac_execution_model(simulation_id, before)
        return self._to_pac_execution(model) if model else None

    def latest_pac_execution_date(self, simulation_id: int) -> date | None:
        return self.session.scalar(
            select(func.max(PacExecutionModel.execution_date)).where(
                PacExecutionModel.simulation_id == simulation_id
            )
        )

    def save_pac_execution_from_simulation(
        self,
        simulation: SavedPacSimulation,
        execution_date: date,
        name: str | None = None,
        manual: bool = False,
        quotes: dict[str, HistoricalPriceQuote] | None = None,
    ) -> PacExecution:
        model = self.session.scalar(
            select(PacExecutionModel).where(
                PacExecutionModel.simulation_id == simulation.id,
                PacExecutionModel.execution_date == execution_date,
            )
        )
        if not model:
            model = PacExecutionModel(
                simulation_id=simulation.id,
                simulation_name=simulation.name,
                execution_schedule=simulation.execution_schedule,
                execution_date=execution_date,
                name=(name or "").strip() or f"Esecuzione PAC {execution_date:%d/%m/%Y}",
                manual=manual,
            )
            self.session.add(model)
            self.session.flush()
        else:
            model.simulation_name = simulation.name
            model.execution_schedule = simulation.execution_schedule
            model.name = (name or model.name).strip() or model.name
            model.manual = bool(manual or model.manual)
            model.rows.clear()

        previous = self._latest_pac_execution_model(simulation.id, before=execution_date)
        previous_prices = {
            row.isin: row.current_price
            for row in previous.rows
            if row.current_price is not None
        } if previous else {}
        quotes = quotes or {}

        for index, row in enumerate(simulation.rows):
            quote = quotes.get(row.metadata.isin)
            current_price = quote.price if quote else None
            previous_price = previous_prices.get(row.metadata.isin)
            price_diff = (
                current_price - previous_price
                if current_price is not None and previous_price is not None
                else None
            )
            price_diff_pct = (
                price_diff / previous_price
                if price_diff is not None and previous_price
                else None
            )
            model.rows.append(
                PacExecutionRowModel(
                    sort_order=index,
                    asset_class=row.asset_class,
                    segment=row.metadata.segment,
                    name=row.metadata.name,
                    isin=row.metadata.isin,
                    invested_amount=float(row.effective_amount),
                    currency=row.metadata.currency,
                    share_price=None,
                    shares=None,
                    current_price=current_price,
                    current_price_date=quote.price_date if quote else None,
                    current_price_source=quote.source if quote else "",
                    previous_price=previous_price,
                    price_diff=price_diff,
                    price_diff_pct=price_diff_pct,
                )
            )
        self.session.flush()
        return self._to_pac_execution(model)

    def update_pac_execution_name(self, execution_id: int, name: str) -> PacExecution:
        model = self.session.get(PacExecutionModel, execution_id)
        if not model:
            raise ValueError(f"PAC execution not found: {execution_id}")
        model.name = name.strip() or model.name
        model.manual = True
        self.session.flush()
        return self._to_pac_execution(model)

    def update_pac_execution_row_amount(self, row_id: int, invested_amount: float) -> PacExecution:
        row = self.session.get(PacExecutionRowModel, row_id)
        if not row:
            raise ValueError(f"PAC execution row not found: {row_id}")
        row.invested_amount = float(invested_amount)
        row.execution.manual = True
        self.session.flush()
        return self._to_pac_execution(row.execution)

    def update_pac_execution_row_details(
        self,
        row_id: int,
        invested_amount: float,
        share_price: float | None,
        shares: float | None,
    ) -> PacExecution:
        row = self.session.get(PacExecutionRowModel, row_id)
        if not row:
            raise ValueError(f"PAC execution row not found: {row_id}")
        row.invested_amount = float(invested_amount)
        row.share_price = float(share_price) if share_price is not None else None
        row.shares = float(shares) if shares is not None else None
        row.execution.manual = True
        self.session.flush()
        return self._to_pac_execution(row.execution)

    def delete_pac_execution(self, execution_id: int) -> None:
        model = self.session.get(PacExecutionModel, execution_id)
        if not model:
            raise ValueError(f"PAC execution not found: {execution_id}")
        self.session.delete(model)

    def save_dashboard_snapshot(self, snapshot: DashboardSnapshot) -> DashboardSnapshot:
        model = DashboardSnapshotModel(
            captured_at=snapshot.captured_at or datetime.now(UTC),
            total_invested=snapshot.total_invested,
            current_value=snapshot.current_value,
            result_value=snapshot.result_value,
            result_pct=snapshot.result_pct,
            latest_live_price_date=snapshot.latest_live_price_date,
            execution_count=snapshot.execution_count,
            etf_count=snapshot.etf_count,
            quote_error_count=snapshot.quote_error_count,
        )
        self.session.add(model)
        self.session.flush()

        for index, row in enumerate(snapshot.rows):
            self.session.add(
                DashboardSnapshotRowModel(
                    snapshot_id=model.id,
                    sort_order=index,
                    asset_class=row.asset_class,
                    segment=row.segment,
                    name=row.name,
                    isin=row.isin,
                    invested_amount=row.invested_amount,
                    units=row.units,
                    missing_data=row.missing_data,
                    live_price=row.live_price,
                    live_price_date=row.live_price_date,
                    live_price_source=row.live_price_source,
                    current_value=row.current_value,
                    result_value=row.result_value,
                    execution_count=row.execution_count,
                )
            )
        self.session.flush()
        return self._to_dashboard_snapshot(model)

    def latest_dashboard_snapshot(self) -> DashboardSnapshot | None:
        model = self.session.scalars(
            select(DashboardSnapshotModel)
            .order_by(DashboardSnapshotModel.captured_at.desc(), DashboardSnapshotModel.id.desc())
            .limit(1)
        ).first()
        return self._to_dashboard_snapshot(model) if model else None

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

    def _latest_pac_execution_model(
        self,
        simulation_id: int,
        before: date | None = None,
    ) -> PacExecutionModel | None:
        stmt = select(PacExecutionModel).where(PacExecutionModel.simulation_id == simulation_id)
        if before is not None:
            stmt = stmt.where(PacExecutionModel.execution_date < before)
        return self.session.scalars(
            stmt.order_by(PacExecutionModel.execution_date.desc(), PacExecutionModel.id.desc()).limit(1)
        ).first()

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
            execution_schedule=model.execution_schedule,
            round_up=model.round_up,
            real_monthly_pac=model.real_monthly_pac,
            created_at=model.created_at,
            updated_at=model.updated_at,
            applied_at=model.applied_at,
            rows=[_to_simulation_row(row) for row in model.rows],
        )

    @staticmethod
    def _to_pac_execution(model: PacExecutionModel) -> PacExecution:
        return PacExecution(
            id=model.id,
            simulation_id=model.simulation_id,
            simulation_name=model.simulation_name,
            execution_schedule=model.execution_schedule,
            name=model.name,
            execution_date=model.execution_date,
            manual=model.manual,
            created_at=model.created_at,
            updated_at=model.updated_at,
            rows=[_to_pac_execution_row(row) for row in model.rows],
        )

    @staticmethod
    def _to_dashboard_snapshot(model: DashboardSnapshotModel) -> DashboardSnapshot:
        return DashboardSnapshot(
            id=model.id,
            captured_at=model.captured_at,
            total_invested=model.total_invested,
            current_value=model.current_value,
            result_value=model.result_value,
            result_pct=model.result_pct,
            latest_live_price_date=model.latest_live_price_date,
            execution_count=model.execution_count,
            etf_count=model.etf_count,
            quote_error_count=model.quote_error_count,
            rows=[
                DashboardSnapshotRow(
                    id=row.id,
                    asset_class=row.asset_class,
                    segment=row.segment,
                    name=row.name,
                    isin=row.isin,
                    invested_amount=row.invested_amount,
                    units=row.units,
                    missing_data=row.missing_data,
                    live_price=row.live_price,
                    live_price_date=row.live_price_date,
                    live_price_source=row.live_price_source,
                    current_value=row.current_value,
                    result_value=row.result_value,
                    execution_count=row.execution_count,
                )
                for row in model.rows
            ],
        )


def _normalize_isin(isin: str) -> str:
    return isin.strip().upper()


def _apply_quote_to_price_fields(model, quote: PriceQuote) -> None:
    model.price = float(quote.price)
    model.price_date = quote.price_date
    model.price_source = quote.source
    if quote.currency:
        model.currency = quote.currency
    if quote.exchange:
        model.exchange = quote.exchange


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


def _to_pac_execution_row(model: PacExecutionRowModel) -> PacExecutionRow:
    return PacExecutionRow(
        id=model.id,
        asset_class=model.asset_class,
        segment=model.segment,
        name=model.name,
        isin=model.isin,
        invested_amount=model.invested_amount,
        currency=model.currency,
        share_price=model.share_price,
        shares=model.shares,
        current_price=model.current_price,
        current_price_date=model.current_price_date,
        current_price_source=model.current_price_source,
        previous_price=model.previous_price,
        price_diff=model.price_diff,
        price_diff_pct=model.price_diff_pct,
    )


def _preview_from_saved(simulation: SavedPacSimulation) -> PacSimulationPreview:
    return PacSimulationPreview(
        monthly_pac=simulation.monthly_pac,
        round_up=simulation.round_up,
        real_monthly_pac=simulation.real_monthly_pac,
        rows=simulation.rows,
        execution_schedule=simulation.execution_schedule,
    )
