from datetime import UTC, datetime

from app.domain import EtfMetadata, PacSimulationRow, SavedPacSimulation
from app.ui.pac_simulation_page import simulation_tree_items
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
