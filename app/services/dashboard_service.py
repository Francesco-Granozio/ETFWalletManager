from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date

from app.domain import DashboardSnapshot, DashboardSnapshotRow, PacExecution, PriceQuote
from app.ui.widgets import asset_class_tag
from app.utils.formatting import date_text, money, pct

ASSET_CLASSES = ("Azioni", "Obbligazioni", "Alternativi")


@dataclass(slots=True)
class DashboardEtfGroup:
    asset_class: str
    segment: str
    name: str
    isin: str
    invested_amount: float = 0
    units: float = 0
    missing_execution_price: bool = False
    live_price: float | None = None
    live_price_date: date | None = None
    live_price_source: str = ""
    execution_ids: set[int] = field(default_factory=set)

    @property
    def current_value(self) -> float | None:
        if self.live_price is None or self.missing_execution_price:
            return None
        return self.units * self.live_price

    @property
    def result_value(self) -> float | None:
        current_value = self.current_value
        if current_value is None:
            return None
        return current_value - self.invested_amount

    @property
    def result_pct(self) -> float | None:
        result_value = self.result_value
        if result_value is None or self.invested_amount == 0:
            return None
        return result_value / self.invested_amount


@dataclass(slots=True)
class DashboardAssetGroup:
    asset_class: str
    invested_amount: float = 0
    execution_ids: set[int] = field(default_factory=set)
    etfs: dict[str, DashboardEtfGroup] = field(default_factory=dict)

    @property
    def current_value(self) -> float | None:
        values = [etf.current_value for etf in self.etfs.values()]
        if not values or any(value is None for value in values):
            return None
        return sum(value for value in values if value is not None)

    @property
    def result_value(self) -> float | None:
        current_value = self.current_value
        if current_value is None:
            return None
        return current_value - self.invested_amount

    @property
    def result_pct(self) -> float | None:
        result_value = self.result_value
        if result_value is None or self.invested_amount == 0:
            return None
        return result_value / self.invested_amount


@dataclass(slots=True)
class DashboardPortfolioSummary:
    total_invested: float
    execution_count: int
    latest_execution: PacExecution | None
    asset_classes: dict[str, DashboardAssetGroup]

    @property
    def etf_count(self) -> int:
        return sum(len(asset.etfs) for asset in self.asset_classes.values())

    @property
    def current_value(self) -> float | None:
        values = [asset.current_value for asset in self.asset_classes.values()]
        if not values or any(value is None for value in values):
            return None
        return sum(value for value in values if value is not None)

    @property
    def result_value(self) -> float | None:
        current_value = self.current_value
        if current_value is None:
            return None
        return current_value - self.total_invested

    @property
    def result_pct(self) -> float | None:
        result_value = self.result_value
        if result_value is None or self.total_invested == 0:
            return None
        return result_value / self.total_invested

    @property
    def latest_live_price_date(self) -> date | None:
        dates = [
            etf.live_price_date
            for asset in self.asset_classes.values()
            for etf in asset.etfs.values()
            if etf.live_price_date is not None
        ]
        return max(dates, default=None)


def build_dashboard_summary(
    executions: list[PacExecution],
    live_quotes: dict[str, PriceQuote] | None = None,
) -> DashboardPortfolioSummary:
    asset_classes: dict[str, DashboardAssetGroup] = {}
    quotes_by_isin = {
        isin.strip().upper(): quote
        for isin, quote in (live_quotes or {}).items()
    }
    latest_execution = max(
        executions,
        key=lambda execution: (execution.execution_date, execution.updated_at, execution.id),
        default=None,
    )

    total_invested = 0.0
    for execution in executions:
        for row in execution.rows:
            amount = row.invested_amount
            total_invested += amount
            asset = asset_classes.setdefault(
                row.asset_class,
                DashboardAssetGroup(asset_class=row.asset_class),
            )
            asset.invested_amount += amount
            asset.execution_ids.add(execution.id)

            isin_key = row.isin.strip().upper() or f"row-{row.id}"
            etf = asset.etfs.setdefault(
                isin_key,
                DashboardEtfGroup(
                    asset_class=row.asset_class,
                    segment=row.segment,
                    name=row.name,
                    isin=row.isin,
                ),
            )
            etf.segment = row.segment or etf.segment
            etf.name = row.name or etf.name
            etf.isin = row.isin or etf.isin
            etf.invested_amount += amount
            if row.has_share_details:
                etf.units += row.shares or 0
            elif row.current_price is not None and row.current_price > 0:
                etf.units += amount / row.current_price
            else:
                etf.missing_execution_price = True
            quote = quotes_by_isin.get(isin_key)
            if quote is not None:
                etf.live_price = quote.price
                etf.live_price_date = quote.price_date
                etf.live_price_source = quote.source
            etf.execution_ids.add(execution.id)

    return DashboardPortfolioSummary(
        total_invested=total_invested,
        execution_count=len(executions),
        latest_execution=latest_execution,
        asset_classes=asset_classes,
    )


def dashboard_snapshot_from_summary(
    summary: DashboardPortfolioSummary,
    errors: dict[str, str],
) -> DashboardSnapshot:
    rows: list[DashboardSnapshotRow] = []
    for asset in _ordered_asset_groups(summary.asset_classes):
        for etf in sorted(asset.etfs.values(), key=lambda item: (item.segment.lower(), item.isin)):
            current_value = etf.current_value
            rows.append(
                DashboardSnapshotRow(
                    asset_class=etf.asset_class,
                    segment=etf.segment,
                    name=etf.name,
                    isin=etf.isin.strip().upper(),
                    invested_amount=etf.invested_amount,
                    units=etf.units,
                    missing_data=current_value is None,
                    live_price=etf.live_price,
                    live_price_date=etf.live_price_date,
                    live_price_source=etf.live_price_source,
                    current_value=current_value,
                    result_value=etf.result_value,
                    execution_count=len(etf.execution_ids),
                )
            )
    return DashboardSnapshot(
        total_invested=summary.total_invested,
        current_value=summary.current_value,
        result_value=summary.result_value,
        result_pct=summary.result_pct,
        latest_live_price_date=summary.latest_live_price_date,
        execution_count=summary.execution_count,
        etf_count=summary.etf_count,
        quote_error_count=len(errors),
        rows=rows,
    )


def dashboard_table_rows(summary: DashboardPortfolioSummary) -> list[tuple[str, list[str], str]]:
    rows: list[tuple[str, list[str], str]] = []
    for asset in _ordered_asset_groups(summary.asset_classes):
        total_pct = _ratio(asset.invested_amount, summary.total_invested)
        rows.append(
            (
                f"asset-{asset.asset_class}",
                [
                    asset.asset_class,
                    pct(total_pct),
                    pct(1 if asset.invested_amount else 0),
                    money(asset.invested_amount),
                    money(asset.current_value),
                    _signed_money(asset.result_value),
                    _signed_pct(asset.result_pct),
                    str(len(asset.execution_ids)),
                    "",
                    "",
                ],
                asset_class_tag(asset.asset_class),
            )
        )

        for etf in sorted(asset.etfs.values(), key=lambda item: (item.segment.lower(), item.isin)):
            rows.append(
                (
                    f"etf-{asset.asset_class}-{etf.isin}",
                    [
                        etf.segment,
                        pct(_ratio(etf.invested_amount, summary.total_invested)),
                        pct(_ratio(etf.invested_amount, asset.invested_amount)),
                        money(etf.invested_amount),
                        money(etf.current_value),
                        _signed_money(etf.result_value),
                        _signed_pct(etf.result_pct),
                        str(len(etf.execution_ids)),
                        etf.name,
                        etf.isin,
                    ],
                    "etf_row",
                )
            )

    rows.append(
        (
            "total",
            [
                "TOTALE",
                pct(1 if summary.total_invested else 0),
                "",
                money(summary.total_invested),
                money(summary.current_value),
                _signed_money(summary.result_value),
                _signed_pct(summary.result_pct),
                str(summary.execution_count),
                "",
                "",
            ],
            asset_class_tag("TOTALE"),
        )
    )
    return rows


def dashboard_meta_text(summary: DashboardPortfolioSummary, errors: dict[str, str]) -> str:
    if summary.latest_execution is None:
        pac_text = "Ultimo update PAC: nessuna esecuzione"
    else:
        execution = summary.latest_execution
        mode = "manuale" if execution.manual else "auto"
        pac_text = (
            f"Ultimo update PAC: {date_text(execution.execution_date)} - {execution.name} | "
            f"{execution.simulation_name} | {mode}"
        )
    live_date = summary.latest_live_price_date
    live_text = f"Prezzi live LS: {date_text(live_date)}" if live_date else "Prezzi live LS: non aggiornati"
    error_text = f" | Errori: {len(errors)}" if errors else ""
    return f"{pac_text} | Esecuzioni: {summary.execution_count} | ETF: {summary.etf_count} | {live_text}{error_text}"


def dashboard_isins(executions: list[PacExecution]) -> list[str]:
    return sorted({
        row.isin.strip().upper()
        for execution in executions
        for row in execution.rows
        if row.isin.strip()
    })


def _result_text(value: float | None, percent: float | None) -> str:
    if value is None:
        return "-"
    return f"{_signed_money(value)} ({_signed_pct(percent)})"


def _signed_money(value: float | None) -> str:
    if value is None:
        return "-"
    if value > 0:
        return f"+{money(value)}"
    return money(value)


def _signed_pct(value: float | None) -> str:
    if value is None:
        return "-"
    if value > 0:
        return f"+{pct(value)}"
    return pct(value)


def _ordered_asset_groups(asset_classes: dict[str, DashboardAssetGroup]) -> list[DashboardAssetGroup]:
    ordered = [asset_classes[asset_class] for asset_class in ASSET_CLASSES if asset_class in asset_classes]
    ordered.extend(
        sorted(
            (
                asset
                for asset_class, asset in asset_classes.items()
                if asset_class not in ASSET_CLASSES
            ),
            key=lambda asset: asset.asset_class.lower(),
        )
    )
    return ordered


def _ratio(value: float, total: float) -> float:
    if total == 0:
        return 0
    return value / total
