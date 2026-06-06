from datetime import date

import pytest

from app.domain import EtfMetadata, PacEtfAllocation
from app.services.pac_simulation_service import (
    PacSimulationValidationError,
    calculate_pac_simulation,
)


def metadata(isin: str, name: str) -> EtfMetadata:
    return EtfMetadata(
        isin=isin,
        name=name,
        segment=name,
        ticker=None,
        exchange="GETTEX",
        currency="EUR",
        ter=0.001,
        price=10,
        price_date=date(2026, 6, 6),
        price_source="justETF",
    )


def test_pac_simulation_calculates_total_allocations_and_rounds_up_amounts():
    etfs = [
        PacEtfAllocation("Azioni", "IE000XZSV718", 0.35),
        PacEtfAllocation("Azioni", "IE000R4ZNTN3", 0.28),
        PacEtfAllocation("Azioni", "LU1681045370", 0.07),
        PacEtfAllocation("Azioni", "IE00BJQRDN15", 0.30),
        PacEtfAllocation("Obbligazioni", "LU1650491282", 0.32),
        PacEtfAllocation("Obbligazioni", "IE00BDBRDM35", 0.68),
        PacEtfAllocation("Alternativi", "IE00B4ND3602", 0.50),
        PacEtfAllocation("Alternativi", "IE00BZ1NCS44", 0.50),
    ]
    metadata_by_isin = {
        item.isin: metadata(item.isin, f"ETF {index}")
        for index, item in enumerate(etfs, start=1)
    }

    preview = calculate_pac_simulation(
        monthly_pac=100,
        asset_allocations={
            "Azioni": 0.65,
            "Obbligazioni": 0.25,
            "Alternativi": 0.10,
        },
        etf_allocations=etfs,
        metadata_by_isin=metadata_by_isin,
        round_up=True,
    )

    assert len(preview.rows) == 8
    assert preview.rows[0].target_pct == pytest.approx(0.2275)
    assert preview.rows[0].nominal_amount == pytest.approx(22.75)
    assert preview.rows[0].effective_amount == 23
    assert preview.rows[1].effective_amount == 19
    assert preview.real_monthly_pac == 102


def test_pac_simulation_rejects_invalid_segment_totals():
    etf = PacEtfAllocation("Azioni", "IE000XZSV718", 0.60)

    with pytest.raises(PacSimulationValidationError, match="Azioni.*100"):
        calculate_pac_simulation(
            monthly_pac=100,
            asset_allocations={
                "Azioni": 1,
                "Obbligazioni": 0,
                "Alternativi": 0,
            },
            etf_allocations=[etf],
            metadata_by_isin={"IE000XZSV718": metadata("IE000XZSV718", "ETF 1")},
            round_up=False,
        )
