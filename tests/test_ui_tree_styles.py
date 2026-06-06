from datetime import UTC, datetime

import pytest

from app.domain import EtfMetadata, PacExecution, PacExecutionRow, PacSimulationRow, PriceQuote, SavedPacSimulation
from app.ui.dashboard import build_dashboard_summary, dashboard_table_rows
from app.ui.pac_executions_page import (
    execution_tree_items,
    trend_arrow,
    trend_cell_text,
    trend_label_background,
    trend_money,
    trend_pct,
)
from app.ui.pac_simulation_page import preview_table_rows, simulation_tree_items
from app.ui.widgets import asset_class_tag, treeview_palette, treeview_tag_colors


def test_treeview_palette_uses_dark_colors_for_dark_mode():
    palette = treeview_palette("Dark")

    assert palette.background == "#111827"
    assert palette.foreground == "#F9FAFB"
    assert palette.heading_background == "#1F2937"
    assert palette.selected_background == "#555080"


def test_asset_class_tag_maps_known_groups():
    assert asset_class_tag("Azioni") == "asset_azioni"
    assert asset_class_tag("Obbligazioni") == "asset_obbligazioni"
    assert asset_class_tag("Alternativi") == "asset_alternativi"
    assert asset_class_tag("TOTALE") == "asset_totale"


def test_simulation_parent_row_uses_requested_dark_color():
    colors = treeview_tag_colors("Dark")

    assert colors["simulation"][0] == "#555080"
    assert "subtotal_row" not in colors


def test_simulation_tree_items_group_etfs_by_asset_class():
    metadata = EtfMetadata(
        isin="IE000XZSV718",
        name="ETF Azionario",
        segment="S&P 500",
        ticker=None,
        exchange="GETTEX",
        currency="EUR",
        ter=0.001,
        price=10,
        price_date=None,
        price_source="justETF",
    )
    simulation = SavedPacSimulation(
        id=1,
        name="PAC attivo",
        monthly_pac=100,
        round_up=False,
        real_monthly_pac=100,
        created_at=datetime(2026, 6, 6, tzinfo=UTC),
        updated_at=datetime(2026, 6, 6, tzinfo=UTC),
        applied_at=None,
        rows=[
            PacSimulationRow(
                asset_class="Azioni",
                asset_class_pct=1,
                segment_pct=1,
                target_pct=1,
                nominal_amount=100,
                effective_amount=100,
                metadata=metadata,
            )
        ],
    )

    items = simulation_tree_items(simulation)

    assert items[0].item_id == "sim-1-asset-Azioni"
    assert items[0].parent_id == "sim-1"
    assert items[0].tag == "asset_azioni"
    assert items[1].parent_id == "sim-1-asset-Azioni"
    assert items[1].text == "S&P 500"
    assert items[1].values[2] == "0,10%"
    assert items[0].values[2] == "0,10%"
    assert len(items) == 2
    assert all("subtotal" not in item.item_id for item in items)


def test_preview_table_rows_include_weighted_ter_on_asset_headers_and_total():
    first = EtfMetadata(
        isin="IE000XZSV718",
        name="ETF Azionario",
        segment="S&P 500",
        ticker=None,
        exchange="GETTEX",
        currency="EUR",
        ter=0.002,
        price=10,
        price_date=None,
        price_source="justETF",
    )
    second = EtfMetadata(
        isin="IE00BDBRDM35",
        name="ETF Bond",
        segment="Global Aggregate",
        ticker=None,
        exchange="GETTEX",
        currency="EUR",
        ter=0.001,
        price=10,
        price_date=None,
        price_source="justETF",
    )
    simulation = SavedPacSimulation(
        id=1,
        name="PAC attivo",
        monthly_pac=100,
        round_up=False,
        real_monthly_pac=100,
        created_at=datetime(2026, 6, 6, tzinfo=UTC),
        updated_at=datetime(2026, 6, 6, tzinfo=UTC),
        applied_at=None,
        rows=[
            PacSimulationRow(
                asset_class="Azioni",
                asset_class_pct=0.6,
                segment_pct=1,
                target_pct=0.6,
                nominal_amount=60,
                effective_amount=60,
                metadata=first,
            ),
            PacSimulationRow(
                asset_class="Obbligazioni",
                asset_class_pct=0.4,
                segment_pct=1,
                target_pct=0.4,
                nominal_amount=40,
                effective_amount=40,
                metadata=second,
            ),
        ],
    )

    rows = preview_table_rows(simulation)
    values_by_id = {item_id: values for item_id, values, _ in rows}

    assert "subtotal-Azioni" not in values_by_id
    assert "subtotal-Obbligazioni" not in values_by_id
    assert values_by_id["asset-Azioni"][5] == "0,12%"
    assert values_by_id["asset-Obbligazioni"][5] == "0,04%"
    assert values_by_id["etf-IE000XZSV718"][5] == "0,20%"
    assert values_by_id["total"][5] == "0,16%"


def test_execution_tree_items_group_etfs_with_asset_headers_and_total():
    execution = PacExecution(
        id=1,
        simulation_id=1,
        simulation_name="PAC attivo",
        execution_schedule="Mensile dal 2 del mese",
        name="Giugno",
        execution_date=datetime(2026, 6, 2, tzinfo=UTC).date(),
        manual=False,
        created_at=datetime(2026, 6, 6, tzinfo=UTC),
        updated_at=datetime(2026, 6, 6, tzinfo=UTC),
        rows=[
            PacExecutionRow(
                id=10,
                asset_class="Azioni",
                segment="S&P 500",
                name="ETF Azionario",
                isin="IE000XZSV718",
                invested_amount=23,
                currency="EUR",
                share_price=15.2445,
                shares=1.50874,
            ),
            PacExecutionRow(
                id=11,
                asset_class="Obbligazioni",
                segment="Government Bond",
                name="ETF Bond",
                isin="LU1650491282",
                invested_amount=8,
                currency="EUR",
                share_price=170,
                shares=0.047059,
            ),
        ],
    )

    items = execution_tree_items(execution)

    assert items[0].item_id == "exec-1-asset-Azioni"
    assert items[0].tag == "asset_azioni"
    assert items[1].parent_id == "exec-1-asset-Azioni"
    assert items[1].tag == "etf_row"
    assert items[2].item_id == "exec-1-asset-Obbligazioni"
    assert items[2].tag == "asset_obbligazioni"
    assert items[3].parent_id == "exec-1-asset-Obbligazioni"
    assert items[3].tag == "etf_row"
    assert items[4].item_id == "exec-1-total"
    assert items[4].text == "TOTALE"
    assert items[4].tag == "asset_totale"
    assert all("subtotal" not in item.item_id for item in items)


def test_execution_tree_items_marks_rows_missing_share_details_with_warning():
    execution = PacExecution(
        id=1,
        simulation_id=1,
        simulation_name="PAC attivo",
        execution_schedule="Mensile dal 2 del mese",
        name="Giugno",
        execution_date=datetime(2026, 6, 2, tzinfo=UTC).date(),
        manual=False,
        created_at=datetime(2026, 6, 6, tzinfo=UTC),
        updated_at=datetime(2026, 6, 6, tzinfo=UTC),
        rows=[
            PacExecutionRow(
                id=10,
                asset_class="Azioni",
                segment="S&P 500",
                name="ETF Azionario",
                isin="IE000XZSV718",
                invested_amount=23,
                currency="EUR",
            ),
            PacExecutionRow(
                id=11,
                asset_class="Azioni",
                segment="MSCI World",
                name="ETF Completo",
                isin="IE000R4ZNTN3",
                invested_amount=12,
                currency="EUR",
                share_price=15.2445,
                shares=1.50874,
            ),
        ],
    )

    items = execution_tree_items(execution)
    missing = next(item for item in items if item.item_id == "execrow-10")
    complete = next(item for item in items if item.item_id == "execrow-11")

    assert missing.text.startswith("⚠ ")
    assert missing.tag == "warning_row"
    assert complete.text == "MSCI World"
    assert complete.tag == "etf_row"
    assert complete.values[3] == "15,2445"
    assert complete.values[4] == "1,508740"


def test_dashboard_summary_aggregates_invested_capital_by_asset_class_and_etf():
    first_execution = PacExecution(
        id=1,
        simulation_id=1,
        simulation_name="PAC attivo",
        execution_schedule="Mensile dal 2 del mese",
        name="Maggio",
        execution_date=datetime(2026, 5, 2, tzinfo=UTC).date(),
        manual=False,
        created_at=datetime(2026, 5, 2, tzinfo=UTC),
        updated_at=datetime(2026, 5, 2, tzinfo=UTC),
        rows=[
            PacExecutionRow(
                id=10,
                asset_class="Azioni",
                segment="S&P 500",
                name="ETF Azionario",
                isin="IE000XZSV718",
                invested_amount=60,
                currency="EUR",
            ),
            PacExecutionRow(
                id=11,
                asset_class="Obbligazioni",
                segment="Aggregate Bond",
                name="ETF Bond",
                isin="IE00BDBRDM35",
                invested_amount=40,
                currency="EUR",
            ),
        ],
    )
    latest_execution = PacExecution(
        id=2,
        simulation_id=1,
        simulation_name="PAC attivo",
        execution_schedule="Mensile dal 2 del mese",
        name="Giugno",
        execution_date=datetime(2026, 6, 2, tzinfo=UTC).date(),
        manual=False,
        created_at=datetime(2026, 6, 2, tzinfo=UTC),
        updated_at=datetime(2026, 6, 2, tzinfo=UTC),
        rows=[
            PacExecutionRow(
                id=12,
                asset_class="Azioni",
                segment="S&P 500",
                name="ETF Azionario",
                isin="IE000XZSV718",
                invested_amount=70,
                currency="EUR",
            ),
            PacExecutionRow(
                id=13,
                asset_class="Alternativi",
                segment="Gold",
                name="ETF Oro",
                isin="IE00B4ND3602",
                invested_amount=30,
                currency="EUR",
            ),
        ],
    )

    summary = build_dashboard_summary([first_execution, latest_execution])
    rows = dashboard_table_rows(summary)
    values_by_id = {item_id: values for item_id, values, _ in rows}
    tags_by_id = {item_id: tag for item_id, _, tag in rows}

    assert summary.total_invested == 200
    assert summary.latest_execution is latest_execution
    assert values_by_id["asset-Azioni"][3] == "130,00 EUR"
    assert values_by_id["etf-Azioni-IE000XZSV718"][1] == "65,00%"
    assert values_by_id["etf-Azioni-IE000XZSV718"][2] == "100,00%"
    assert values_by_id["asset-Obbligazioni"][3] == "40,00 EUR"
    assert values_by_id["asset-Alternativi"][3] == "30,00 EUR"
    assert values_by_id["total"][3] == "200,00 EUR"
    assert values_by_id["total"][7] == "2"
    assert tags_by_id["asset-Azioni"] == "asset_azioni"
    assert tags_by_id["total"] == "asset_totale"
    assert "subtotal-Azioni" not in values_by_id


def test_dashboard_summary_uses_live_justetf_quotes_to_calculate_results():
    execution = PacExecution(
        id=1,
        simulation_id=1,
        simulation_name="PAC attivo",
        execution_schedule="Mensile dal 2 del mese",
        name="Giugno",
        execution_date=datetime(2026, 6, 2, tzinfo=UTC).date(),
        manual=False,
        created_at=datetime(2026, 6, 2, tzinfo=UTC),
        updated_at=datetime(2026, 6, 2, tzinfo=UTC),
        rows=[
            PacExecutionRow(
                id=10,
                asset_class="Azioni",
                segment="S&P 500",
                name="ETF Azionario",
                isin="IE000XZSV718",
                invested_amount=100,
                currency="EUR",
                current_price=10,
                current_price_date=datetime(2026, 6, 2, tzinfo=UTC).date(),
                current_price_source="justETF chart",
            ),
            PacExecutionRow(
                id=11,
                asset_class="Azioni",
                segment="S&P 500",
                name="ETF Azionario",
                isin="IE000XZSV718",
                invested_amount=60,
                currency="EUR",
                current_price=12,
                current_price_date=datetime(2026, 6, 2, tzinfo=UTC).date(),
                current_price_source="justETF chart",
            ),
        ],
    )

    summary = build_dashboard_summary(
        [execution],
        live_quotes={
            "IE000XZSV718": PriceQuote(
                isin="IE000XZSV718",
                price=14,
                price_date=datetime(2026, 6, 6, tzinfo=UTC).date(),
                source="justETF Gettex",
            )
        },
    )
    rows = dashboard_table_rows(summary)
    values_by_id = {item_id: values for item_id, values, _ in rows}

    assert summary.current_value == 210
    assert summary.result_value == 50
    assert values_by_id["etf-Azioni-IE000XZSV718"][4] == "210,00 EUR"
    assert values_by_id["etf-Azioni-IE000XZSV718"][5] == "+50,00 EUR"
    assert values_by_id["etf-Azioni-IE000XZSV718"][6] == "+31,25%"
    assert values_by_id["asset-Azioni"][4] == "210,00 EUR"
    assert values_by_id["total"][4] == "210,00 EUR"


def test_dashboard_summary_prefers_manual_shares_over_estimated_units():
    execution = PacExecution(
        id=1,
        simulation_id=1,
        simulation_name="PAC attivo",
        execution_schedule="Mensile dal 2 del mese",
        name="Giugno",
        execution_date=datetime(2026, 6, 2, tzinfo=UTC).date(),
        manual=False,
        created_at=datetime(2026, 6, 2, tzinfo=UTC),
        updated_at=datetime(2026, 6, 2, tzinfo=UTC),
        rows=[
            PacExecutionRow(
                id=10,
                asset_class="Azioni",
                segment="S&P 500",
                name="ETF Azionario",
                isin="IE000XZSV718",
                invested_amount=23,
                currency="EUR",
                current_price=10,
                share_price=15.2445,
                shares=1.50874,
            ),
        ],
    )

    summary = build_dashboard_summary(
        [execution],
        live_quotes={
            "IE000XZSV718": PriceQuote(
                isin="IE000XZSV718",
                price=20,
                price_date=datetime(2026, 6, 6, tzinfo=UTC).date(),
                source="justETF Gettex",
            )
        },
    )

    assert summary.current_value == pytest.approx(30.1748)
    assert summary.result_value == pytest.approx(7.1748)


def test_execution_diff_values_show_direction_indicators():
    assert trend_arrow(2.5).arrow == "▲"
    assert trend_arrow(-2.5).arrow == "▼"
    assert trend_cell_text(-2.5, trend_money).startswith("      ")
    assert trend_money(2.5) == "+2,50 EUR"
    assert trend_money(-2.5) == "-2,50 EUR"
    assert trend_pct(0.125) == "+12,50%"
    assert trend_pct(-0.125) == "-12,50%"
    assert trend_money(None) == "-"
    assert trend_label_background(("etf_row",), selected=True, appearance_mode="Dark") == "#555080"
    assert trend_label_background(("etf_row",), selected=False, appearance_mode="Dark") == "#111827"
