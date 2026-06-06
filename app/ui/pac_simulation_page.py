from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime
from tkinter import messagebox, ttk

import customtkinter as ctk

from app.app_context import AppContext
from app.domain import PacEtfAllocation, PacSimulationPreview, SavedPacSimulation
from app.services.pac_simulation_service import PacSimulationValidationError
from app.ui.widgets import DataTable, asset_class_tag, configure_treeview_tags, configure_treeview_theme
from app.utils.formatting import money, parse_decimal, pct

ASSET_CLASSES = ("Azioni", "Obbligazioni", "Alternativi")


@dataclass(frozen=True, slots=True)
class SimulationTreeItem:
    item_id: str
    parent_id: str
    text: str
    values: tuple[str, str, str, str]
    tag: str
    open: bool = False


class PacSimulationPage(ctk.CTkFrame):
    def __init__(self, master, context: AppContext):
        super().__init__(master, fg_color="transparent")
        self.context = context
        self.preview: PacSimulationPreview | None = None
        self.saved_simulations: list[SavedPacSimulation] = []
        self.row_frames: dict[str, ctk.CTkFrame] = {}
        self.etf_rows: dict[str, list[dict[str, object]]] = {asset: [] for asset in ASSET_CLASSES}

        ctk.CTkLabel(self, text="Simula ripartizione", font=ctk.CTkFont(size=24, weight="bold")).grid(
            row=0,
            column=0,
            columnspan=2,
            sticky="w",
            padx=18,
            pady=(18, 10),
        )

        controls = ctk.CTkScrollableFrame(self, width=430, corner_radius=6)
        controls.grid(row=1, column=0, sticky="nsew", padx=(18, 8), pady=(0, 18))
        controls.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(controls, text="PAC mensile", font=ctk.CTkFont(size=16, weight="bold")).grid(
            row=0,
            column=0,
            columnspan=2,
            sticky="w",
            padx=14,
            pady=(14, 8),
        )
        self.pac_entry = _entry(controls, "Importo", 1)
        self.name_entry = _entry(controls, "Nome simulazione", 2)

        ctk.CTkLabel(controls, text="Asset class", font=ctk.CTkFont(size=16, weight="bold")).grid(
            row=3,
            column=0,
            columnspan=2,
            sticky="w",
            padx=14,
            pady=(18, 8),
        )
        self.asset_entries: dict[str, ctk.CTkEntry] = {}
        for offset, asset_class in enumerate(ASSET_CLASSES, start=4):
            self.asset_entries[asset_class] = _entry(controls, f"{asset_class} %", offset)

        self.round_up = ctk.CTkSwitch(controls, text="Arrotonda importi per eccesso")
        self.round_up.grid(row=7, column=0, columnspan=2, sticky="w", padx=14, pady=(12, 8))

        ctk.CTkLabel(controls, text="ETF", font=ctk.CTkFont(size=16, weight="bold")).grid(
            row=8,
            column=0,
            columnspan=2,
            sticky="w",
            padx=14,
            pady=(18, 8),
        )
        self.tabs = ctk.CTkTabview(controls)
        self.tabs.grid(row=9, column=0, columnspan=2, sticky="nsew", padx=14, pady=(0, 12))
        for asset_class in ASSET_CLASSES:
            tab = self.tabs.add(asset_class)
            tab.grid_columnconfigure(0, weight=1)
            ctk.CTkButton(
                tab,
                text="Aggiungi ETF",
                command=lambda selected=asset_class: self.add_etf_row(selected),
            ).grid(row=0, column=0, sticky="ew", padx=6, pady=(8, 6))
            rows_frame = ctk.CTkFrame(tab, fg_color="transparent")
            rows_frame.grid(row=1, column=0, sticky="nsew", padx=0, pady=0)
            rows_frame.grid_columnconfigure(0, weight=1)
            self.row_frames[asset_class] = rows_frame
            self.add_etf_row(asset_class)

        ctk.CTkButton(controls, text="Nuova simulazione", command=self.new_simulation).grid(
            row=10,
            column=0,
            columnspan=2,
            sticky="ew",
            padx=14,
            pady=(8, 6),
        )
        ctk.CTkButton(controls, text="Calcola preview", command=self.calculate_preview).grid(
            row=11,
            column=0,
            columnspan=2,
            sticky="ew",
            padx=14,
            pady=6,
        )
        ctk.CTkButton(controls, text="Aggiorna dati justETF", command=self.refresh_metadata).grid(
            row=12,
            column=0,
            columnspan=2,
            sticky="ew",
            padx=14,
            pady=6,
        )
        ctk.CTkButton(controls, text="Salva simulazione", command=self.save_simulation).grid(
            row=13,
            column=0,
            columnspan=2,
            sticky="ew",
            padx=14,
            pady=6,
        )
        ctk.CTkButton(controls, text="Applica preview al PAC", command=self.create_pac).grid(
            row=14,
            column=0,
            columnspan=2,
            sticky="ew",
            padx=14,
            pady=(6, 16),
        )

        preview_panel = ctk.CTkFrame(self, corner_radius=6)
        preview_panel.grid(row=1, column=1, sticky="nsew", padx=(8, 18), pady=(0, 18))
        preview_panel.grid_columnconfigure(0, weight=1)
        preview_panel.grid_rowconfigure(2, weight=1)
        preview_panel.grid_rowconfigure(4, weight=2)
        self.summary_label = ctk.CTkLabel(preview_panel, text="PAC nominale: -", anchor="w")
        self.summary_label.grid(row=0, column=0, sticky="ew", padx=14, pady=(14, 8))

        saved_header = ctk.CTkFrame(preview_panel, fg_color="transparent")
        saved_header.grid(row=1, column=0, sticky="ew", padx=14, pady=(4, 6))
        saved_header.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(saved_header, text="Simulazioni salvate", font=ctk.CTkFont(size=16, weight="bold")).grid(
            row=0,
            column=0,
            sticky="w",
        )
        ctk.CTkButton(saved_header, text="Carica", width=90, command=self.load_selected_simulation).grid(
            row=0,
            column=1,
            padx=4,
        )
        ctk.CTkButton(saved_header, text="Applica", width=90, command=self.apply_selected_simulation).grid(
            row=0,
            column=2,
            padx=4,
        )
        ctk.CTkButton(
            saved_header,
            text="Elimina",
            width=90,
            fg_color="#B91C1C",
            hover_color="#991B1B",
            command=self.delete_selected_simulation,
        ).grid(
            row=0,
            column=3,
            padx=(4, 0),
        )
        saved_frame = ctk.CTkFrame(preview_panel, corner_radius=6)
        saved_frame.grid(row=2, column=0, sticky="nsew", padx=14, pady=(0, 12))
        saved_frame.grid_rowconfigure(0, weight=1)
        saved_frame.grid_columnconfigure(0, weight=1)
        self.saved_tree = ttk.Treeview(
            saved_frame,
            columns=("pac", "real", "rows", "applied"),
            show="tree headings",
            height=8,
            selectmode="browse",
        )
        configure_treeview_theme(self.saved_tree, "SavedPac.Treeview")
        self.saved_tree.heading("#0", text="Simulazione / ETF")
        self.saved_tree.heading("pac", text="PAC")
        self.saved_tree.heading("real", text="Reale")
        self.saved_tree.heading("rows", text="ETF")
        self.saved_tree.heading("applied", text="Applicata")
        self.saved_tree.column("#0", width=330, minwidth=180)
        self.saved_tree.column("pac", width=100, minwidth=80)
        self.saved_tree.column("real", width=100, minwidth=80)
        self.saved_tree.column("rows", width=60, minwidth=50)
        self.saved_tree.column("applied", width=120, minwidth=90)
        saved_scroll = ttk.Scrollbar(saved_frame, orient="vertical", command=self.saved_tree.yview)
        self.saved_tree.configure(yscrollcommand=saved_scroll.set)
        self.saved_tree.grid(row=0, column=0, sticky="nsew")
        saved_scroll.grid(row=0, column=1, sticky="ns")

        ctk.CTkLabel(preview_panel, text="Preview", font=ctk.CTkFont(size=16, weight="bold")).grid(
            row=3,
            column=0,
            sticky="w",
            padx=14,
            pady=(2, 6),
        )
        self.table = DataTable(
            preview_panel,
            [
                ("asset", "Asset Class", 150),
                ("total_pct", "% Allocazione Totale", 130),
                ("segment_pct", "% Allocazione Segmento", 150),
                ("nominal", "Importo PAC", 110),
                ("effective", "Importo Reale", 110),
                ("name", "Strumento", 320),
                ("isin", "ISIN", 130),
            ],
        )
        self.table.grid(row=4, column=0, sticky="nsew", padx=14, pady=(0, 14))

        self.grid_columnconfigure(0, weight=0)
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(1, weight=1)

    def refresh(self) -> None:
        if not self.pac_entry.get().strip():
            monthly_pac = self.context.monthly_pac()
            if monthly_pac:
                _replace(self.pac_entry, str(monthly_pac))
        self.refresh_saved_simulations()

    def add_etf_row(self, asset_class: str) -> dict[str, object]:
        frame = ctk.CTkFrame(self.row_frames[asset_class], corner_radius=6)
        row_index = len(self.etf_rows[asset_class])
        frame.grid(row=row_index, column=0, sticky="ew", padx=0, pady=5)
        frame.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(frame, text="ISIN").grid(row=0, column=0, sticky="w", padx=(10, 6), pady=(8, 4))
        isin_entry = ctk.CTkEntry(frame, width=140)
        isin_entry.grid(row=0, column=1, sticky="ew", padx=6, pady=(8, 4))
        ctk.CTkLabel(frame, text="%").grid(row=1, column=0, sticky="w", padx=(10, 6), pady=(4, 8))
        percent_entry = ctk.CTkEntry(frame, width=90)
        percent_entry.grid(row=1, column=1, sticky="w", padx=6, pady=(4, 8))
        ctk.CTkButton(frame, text="X", width=34, command=lambda: self.remove_etf_row(asset_class, frame)).grid(
            row=0,
            column=2,
            rowspan=2,
            padx=(6, 10),
            pady=8,
        )
        row = {
            "frame": frame,
            "isin": isin_entry,
            "percent": percent_entry,
        }
        self.etf_rows[asset_class].append(row)
        return row

    def remove_etf_row(self, asset_class: str, frame: ctk.CTkFrame) -> None:
        self.etf_rows[asset_class] = [
            row for row in self.etf_rows[asset_class] if row["frame"] is not frame
        ]
        frame.destroy()

    def calculate_preview(self) -> None:
        self._build_preview(force_refresh=False)

    def refresh_metadata(self) -> None:
        self._build_preview(force_refresh=True)

    def new_simulation(self) -> None:
        self.preview = None
        _replace(self.pac_entry, "")
        _replace(self.name_entry, "")
        for entry in self.asset_entries.values():
            _replace(entry, "")
        self._clear_etf_rows()
        for asset_class in ASSET_CLASSES:
            self.add_etf_row(asset_class)
        self.round_up.deselect()
        self.summary_label.configure(text="PAC nominale: -")
        self.table.set_rows([])

    def save_simulation(self) -> None:
        preview = self._build_preview(force_refresh=False)
        if preview is None:
            return
        saved = self.context.save_simulation_preview(preview, self.name_entry.get())
        self.refresh_saved_simulations()
        messagebox.showinfo("Simulazione", f"Simulazione salvata: {saved.name}.")

    def create_pac(self) -> None:
        preview = self._build_preview(force_refresh=False)
        if preview is None:
            return
        confirmed = messagebox.askyesno(
            "Crea PAC",
            "Il portafoglio esistente verra sostituito con questa ripartizione. Continuare?",
        )
        if not confirmed:
            return
        self.context.save_pac_simulation(preview, self.name_entry.get())
        self.refresh_saved_simulations()
        messagebox.showinfo("Crea PAC", f"PAC creato: {money(preview.real_monthly_pac)}.")

    def load_selected_simulation(self) -> None:
        simulation = self._selected_saved_simulation()
        if simulation is None:
            messagebox.showinfo("Simulazioni", "Seleziona prima una simulazione.")
            return
        self._populate_form(simulation)
        self.preview = _preview_from_saved(simulation)
        self._render_preview(self.preview)

    def apply_selected_simulation(self) -> None:
        simulation = self._selected_saved_simulation()
        if simulation is None:
            messagebox.showinfo("Simulazioni", "Seleziona prima una simulazione.")
            return
        confirmed = messagebox.askyesno(
            "Applica PAC",
            f"Applicare '{simulation.name}' come PAC attivo?",
        )
        if not confirmed:
            return
        applied = self.context.apply_saved_simulation(simulation.id)
        self.refresh_saved_simulations()
        messagebox.showinfo("Applica PAC", f"PAC attivo: {applied.name}.")

    def delete_selected_simulation(self) -> None:
        simulation = self._selected_saved_simulation()
        if simulation is None:
            messagebox.showinfo("Simulazioni", "Seleziona prima una simulazione.")
            return
        confirmed = messagebox.askyesno(
            "Elimina PAC",
            f"Eliminare la simulazione '{simulation.name}'?",
        )
        if not confirmed:
            return
        self.context.delete_saved_simulation(simulation.id)
        if self.preview is not None and self.name_entry.get().strip() == simulation.name:
            self.new_simulation()
        self.refresh_saved_simulations()
        messagebox.showinfo("Elimina PAC", "Simulazione eliminata.")

    def refresh_saved_simulations(self) -> None:
        self.saved_simulations = self.context.saved_pac_simulations()
        self.saved_tree.delete(*self.saved_tree.get_children())
        configure_treeview_tags(self.saved_tree)
        for simulation in self.saved_simulations:
            parent_id = f"sim-{simulation.id}"
            self.saved_tree.insert(
                "",
                "end",
                iid=parent_id,
                text=simulation.name,
                open=False,
                tags=("simulation",),
                values=(
                    money(simulation.monthly_pac),
                    money(simulation.real_monthly_pac),
                    str(len(simulation.rows)),
                    _datetime_text(simulation.applied_at),
                ),
            )
            for item in simulation_tree_items(simulation):
                self.saved_tree.insert(
                    item.parent_id,
                    "end",
                    iid=item.item_id,
                    text=item.text,
                    values=item.values,
                    tags=(item.tag,),
                    open=item.open,
                )

    def _build_preview(self, force_refresh: bool) -> PacSimulationPreview | None:
        try:
            monthly_pac = parse_decimal(self.pac_entry.get())
            asset_allocations = self._asset_allocations()
            etf_allocations = self._etf_allocations()
            preview = self.context.simulate_pac(
                monthly_pac=monthly_pac,
                asset_allocations=asset_allocations,
                etf_allocations=etf_allocations,
                round_up=bool(self.round_up.get()),
                force_refresh=force_refresh,
            )
        except PacSimulationValidationError as exc:
            messagebox.showerror("Simula ripartizione", str(exc))
            return None
        except ValueError:
            messagebox.showerror("Simula ripartizione", "Inserisci importi e percentuali validi.")
            return None
        except Exception as exc:
            messagebox.showerror("justETF", str(exc) or exc.__class__.__name__)
            return None

        self.preview = preview
        self._render_preview(preview)
        return preview

    def _asset_allocations(self) -> dict[str, float]:
        return {
            asset_class: _parse_percent(self.asset_entries[asset_class].get())
            for asset_class in ASSET_CLASSES
        }

    def _etf_allocations(self) -> list[PacEtfAllocation]:
        allocations: list[PacEtfAllocation] = []
        for asset_class in ASSET_CLASSES:
            for row in self.etf_rows[asset_class]:
                isin_entry = row["isin"]
                percent_entry = row["percent"]
                isin = isin_entry.get().strip() if isinstance(isin_entry, ctk.CTkEntry) else ""
                percent_text = percent_entry.get().strip() if isinstance(percent_entry, ctk.CTkEntry) else ""
                if not isin and not percent_text:
                    continue
                if not isin or not percent_text:
                    raise ValueError("ETF incompleto")
                allocations.append(PacEtfAllocation(asset_class, isin, _parse_percent(percent_text)))
        return allocations

    def _render_preview(self, preview: PacSimulationPreview) -> None:
        effective_label = (
            f" | PAC reale: {money(preview.real_monthly_pac)}"
            if preview.round_up
            else ""
        )
        self.summary_label.configure(text=f"PAC nominale: {money(preview.monthly_pac)}{effective_label}")

        rows = []
        by_asset: dict[str, list] = defaultdict(list)
        for row in preview.rows:
            by_asset[row.asset_class].append(row)

        for asset_class in ASSET_CLASSES:
            asset_rows = by_asset.get(asset_class, [])
            if not asset_rows:
                continue
            asset_pct = asset_rows[0].asset_class_pct
            nominal = sum(row.nominal_amount for row in asset_rows)
            effective = sum(row.effective_amount for row in asset_rows)
            rows.append(
                (
                    f"asset-{asset_class}",
                    [
                        asset_class,
                        pct(asset_pct),
                        pct(1),
                        money(nominal),
                        money(effective),
                        "",
                        "",
                    ],
                    asset_class_tag(asset_class),
                )
            )
            for item in asset_rows:
                rows.append(
                    (
                        f"etf-{item.metadata.isin}",
                        [
                            item.metadata.segment,
                            pct(item.target_pct),
                            pct(item.segment_pct),
                            money(item.nominal_amount),
                            money(item.effective_amount),
                            item.metadata.name,
                            item.metadata.isin,
                        ],
                        "etf_row",
                    )
                )

        rows.append(
            (
                "total",
                [
                    "TOTALE",
                    pct(1),
                    "",
                    money(preview.monthly_pac),
                    money(preview.real_monthly_pac),
                    "",
                    "",
                ],
                asset_class_tag("TOTALE"),
            )
        )
        self.table.set_rows(rows)

    def _clear_etf_rows(self) -> None:
        for asset_class in ASSET_CLASSES:
            for row in self.etf_rows[asset_class]:
                frame = row["frame"]
                if isinstance(frame, ctk.CTkFrame):
                    frame.destroy()
            self.etf_rows[asset_class] = []

    def _populate_form(self, simulation: SavedPacSimulation) -> None:
        _replace(self.name_entry, simulation.name)
        _replace(self.pac_entry, str(simulation.monthly_pac))
        for asset_class in ASSET_CLASSES:
            asset_row = next((row for row in simulation.rows if row.asset_class == asset_class), None)
            _replace(self.asset_entries[asset_class], str((asset_row.asset_class_pct * 100) if asset_row else 0))
        if simulation.round_up:
            self.round_up.select()
        else:
            self.round_up.deselect()
        self._clear_etf_rows()
        for asset_class in ASSET_CLASSES:
            rows = [row for row in simulation.rows if row.asset_class == asset_class]
            if not rows:
                self.add_etf_row(asset_class)
                continue
            for row in rows:
                entries = self.add_etf_row(asset_class)
                isin_entry = entries["isin"]
                percent_entry = entries["percent"]
                if isinstance(isin_entry, ctk.CTkEntry):
                    _replace(isin_entry, row.metadata.isin)
                if isinstance(percent_entry, ctk.CTkEntry):
                    _replace(percent_entry, str(row.segment_pct * 100))

    def _selected_saved_simulation(self) -> SavedPacSimulation | None:
        selection = self.saved_tree.selection()
        if not selection:
            return None
        item_id = selection[0]
        if "-row-" in item_id:
            item_id = self.saved_tree.parent(item_id)
        if not item_id.startswith("sim-"):
            return None
        try:
            simulation_id = int(item_id.removeprefix("sim-"))
        except ValueError:
            return None
        return next((simulation for simulation in self.saved_simulations if simulation.id == simulation_id), None)


def _entry(master, label: str, row: int) -> ctk.CTkEntry:
    ctk.CTkLabel(master, text=label).grid(row=row, column=0, sticky="w", padx=14, pady=6)
    entry = ctk.CTkEntry(master)
    entry.grid(row=row, column=1, sticky="ew", padx=(6, 14), pady=6)
    return entry


def _replace(entry: ctk.CTkEntry, value: str) -> None:
    entry.delete(0, "end")
    entry.insert(0, value.replace(".", ","))


def _parse_percent(text: str) -> float:
    value = parse_decimal(text.replace("%", ""))
    return value / 100


def simulation_tree_items(simulation: SavedPacSimulation) -> list[SimulationTreeItem]:
    items: list[SimulationTreeItem] = []
    rows_by_asset: dict[str, list] = defaultdict(list)
    for row in simulation.rows:
        rows_by_asset[row.asset_class].append(row)

    for asset_class in ASSET_CLASSES:
        asset_rows = rows_by_asset.get(asset_class, [])
        if not asset_rows:
            continue
        asset_id = f"sim-{simulation.id}-asset-{asset_class}"
        nominal = sum(row.nominal_amount for row in asset_rows)
        effective = sum(row.effective_amount for row in asset_rows)
        items.append(
            SimulationTreeItem(
                item_id=asset_id,
                parent_id=f"sim-{simulation.id}",
                text=asset_class,
                values=(
                    pct(asset_rows[0].asset_class_pct),
                    money(effective),
                    str(len(asset_rows)),
                    "",
                ),
                tag=asset_class_tag(asset_class),
                open=True,
            )
        )
        for index, row in enumerate(asset_rows, start=1):
            items.append(
                SimulationTreeItem(
                    item_id=f"{asset_id}-row-{index}",
                    parent_id=asset_id,
                    text=row.metadata.segment,
                    values=(
                        pct(row.target_pct),
                        money(row.effective_amount),
                        row.metadata.isin,
                        "",
                    ),
                    tag="etf_row",
                )
            )
    return items


def _preview_from_saved(simulation: SavedPacSimulation) -> PacSimulationPreview:
    return PacSimulationPreview(
        monthly_pac=simulation.monthly_pac,
        round_up=simulation.round_up,
        real_monthly_pac=simulation.real_monthly_pac,
        rows=simulation.rows,
    )


def _datetime_text(value: datetime | None) -> str:
    if value is None:
        return "-"
    return value.strftime("%d/%m/%Y %H:%M")
