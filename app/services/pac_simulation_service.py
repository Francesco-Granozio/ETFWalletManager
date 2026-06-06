from __future__ import annotations

from collections import Counter, defaultdict
from math import ceil, isclose
import re

from app.domain import (
    EtfMetadata,
    PacEtfAllocation,
    PacSimulationPreview,
    PacSimulationRow,
)

ISIN_PATTERN = re.compile(r"^[A-Z]{2}[A-Z0-9]{9}[0-9]$")


class PacSimulationValidationError(ValueError):
    pass


def calculate_pac_simulation(
    monthly_pac: float,
    asset_allocations: dict[str, float],
    etf_allocations: list[PacEtfAllocation],
    metadata_by_isin: dict[str, EtfMetadata],
    round_up: bool = False,
) -> PacSimulationPreview:
    _validate_monthly_pac(monthly_pac)
    normalized_assets = {asset_class: float(value) for asset_class, value in asset_allocations.items()}
    normalized_etfs = [
        PacEtfAllocation(item.asset_class, item.isin.strip().upper(), float(item.segment_pct))
        for item in etf_allocations
    ]
    _validate_assets(normalized_assets)
    _validate_etfs(normalized_assets, normalized_etfs, metadata_by_isin)

    rows: list[PacSimulationRow] = []
    for item in normalized_etfs:
        asset_pct = normalized_assets[item.asset_class]
        target_pct = asset_pct * item.segment_pct
        nominal_amount = round(monthly_pac * target_pct, 2)
        effective_amount = float(ceil(nominal_amount)) if round_up else nominal_amount
        rows.append(
            PacSimulationRow(
                asset_class=item.asset_class,
                asset_class_pct=asset_pct,
                segment_pct=item.segment_pct,
                target_pct=target_pct,
                nominal_amount=nominal_amount,
                effective_amount=effective_amount,
                metadata=metadata_by_isin[item.isin],
            )
        )

    real_monthly_pac = sum(row.effective_amount for row in rows) if round_up else monthly_pac
    return PacSimulationPreview(
        monthly_pac=round(monthly_pac, 2),
        round_up=round_up,
        real_monthly_pac=round(real_monthly_pac, 2),
        rows=rows,
    )


def _validate_monthly_pac(monthly_pac: float) -> None:
    if monthly_pac <= 0:
        raise PacSimulationValidationError("Il PAC mensile deve essere maggiore di zero.")


def _validate_assets(asset_allocations: dict[str, float]) -> None:
    if not asset_allocations:
        raise PacSimulationValidationError("Inserisci almeno una asset class.")
    invalid = [asset for asset, value in asset_allocations.items() if value < 0]
    if invalid:
        raise PacSimulationValidationError(f"Allocazione negativa per: {', '.join(invalid)}.")
    total = sum(asset_allocations.values())
    if not isclose(total, 1.0, abs_tol=0.0001):
        raise PacSimulationValidationError("La ripartizione delle asset class deve totalizzare 100%.")


def _validate_etfs(
    asset_allocations: dict[str, float],
    etf_allocations: list[PacEtfAllocation],
    metadata_by_isin: dict[str, EtfMetadata],
) -> None:
    if not etf_allocations:
        raise PacSimulationValidationError("Inserisci almeno un ETF.")

    invalid_isins = [item.isin for item in etf_allocations if not ISIN_PATTERN.match(item.isin)]
    if invalid_isins:
        raise PacSimulationValidationError(f"ISIN non validi: {', '.join(invalid_isins)}.")

    duplicate_isins = [isin for isin, count in Counter(item.isin for item in etf_allocations).items() if count > 1]
    if duplicate_isins:
        raise PacSimulationValidationError(f"ISIN duplicati: {', '.join(duplicate_isins)}.")

    unknown_assets = sorted({item.asset_class for item in etf_allocations if item.asset_class not in asset_allocations})
    if unknown_assets:
        raise PacSimulationValidationError(f"Asset class non configurate: {', '.join(unknown_assets)}.")

    missing_metadata = [item.isin for item in etf_allocations if item.isin not in metadata_by_isin]
    if missing_metadata:
        raise PacSimulationValidationError(f"Metadata justETF mancanti: {', '.join(missing_metadata)}.")

    segment_totals: dict[str, float] = defaultdict(float)
    for item in etf_allocations:
        if item.segment_pct <= 0:
            raise PacSimulationValidationError(f"La percentuale di {item.isin} deve essere maggiore di zero.")
        segment_totals[item.asset_class] += item.segment_pct

    for asset_class, asset_pct in asset_allocations.items():
        segment_total = segment_totals.get(asset_class, 0.0)
        if asset_pct > 0 and not isclose(segment_total, 1.0, abs_tol=0.0001):
            raise PacSimulationValidationError(
                f"La ripartizione ETF di {asset_class} deve totalizzare 100%."
            )
        if asset_pct == 0 and segment_total > 0:
            raise PacSimulationValidationError(
                f"{asset_class} ha allocazione 0%, quindi non puo contenere ETF."
            )
