from datetime import UTC, datetime

from app.domain import EtfMetadata, PacExecution, PacExecutionRow, PacSimulationRow, SavedPacSimulation
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
    assert colors["subtotal_row"][0] == "#0E7490"


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
    assert items[2].parent_id == "sim-1-asset-Azioni"
    assert items[2].text == "Subtotale Azioni"
    assert items[2].values[2] == "0,10%"
    assert items[2].tag == "subtotal_row"


def test_preview_table_rows_include_weighted_ter_subtotals_and_total():
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

    assert values_by_id["etf-IE000XZSV718"][5] == "0,20%"
    assert values_by_id["subtotal-Azioni"][5] == "0,12%"
    assert values_by_id["subtotal-Obbligazioni"][5] == "0,04%"
    assert values_by_id["total"][5] == "0,16%"


def test_execution_tree_items_group_etfs_with_subtotals_and_total():
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
                asset_class="Obbligazioni",
                segment="Government Bond",
                name="ETF Bond",
                isin="LU1650491282",
                invested_amount=8,
                currency="EUR",
            ),
        ],
    )

    items = execution_tree_items(execution)

    assert items[0].item_id == "exec-1-asset-Azioni"
    assert items[0].tag == "asset_azioni"
    assert items[1].parent_id == "exec-1-asset-Azioni"
    assert items[1].tag == "etf_row"
    assert items[2].parent_id == "exec-1-asset-Azioni"
    assert items[2].text == "Subtotale Azioni"
    assert items[2].tag == "subtotal_row"
    assert items[3].item_id == "exec-1-asset-Obbligazioni"
    assert items[3].tag == "asset_obbligazioni"
    assert items[4].parent_id == "exec-1-asset-Obbligazioni"
    assert items[4].tag == "etf_row"
    assert items[5].parent_id == "exec-1-asset-Obbligazioni"
    assert items[5].text == "Subtotale Obbligazioni"
    assert items[5].tag == "subtotal_row"
    assert items[6].item_id == "exec-1-total"
    assert items[6].text == "TOTALE"
    assert items[6].tag == "asset_totale"


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
