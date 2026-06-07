from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import date
import tkinter as tk
from tkinter import messagebox, ttk

import customtkinter as ctk

from app.app_context import AppContext
from app.domain import PacExecution, PacExecutionRow, SavedPacSimulation
from app.ui.widgets import (
    asset_class_tag,
    configure_treeview_tags,
    configure_treeview_theme,
    treeview_palette,
    treeview_tag_colors,
)
from app.utils.formatting import date_text, money, number, parse_decimal, pct

TREND_UP_COLOR = "#22C55E"
TREND_DOWN_COLOR = "#EF4444"


@dataclass(frozen=True, slots=True)
class TrendArrow:
    arrow: str
    color: str


@dataclass(frozen=True, slots=True)
class ExecutionTreeItem:
    item_id: str
    parent_id: str
    text: str
    values: tuple[str, ...]
    tag: str
    open: bool = False
    trends: tuple[tuple[str, TrendArrow], ...] = ()


class PacExecutionsPage(ctk.CTkFrame):
    def __init__(self, master, context: AppContext):
        super().__init__(master, fg_color="transparent")
        self.context = context
        self.executions: list[PacExecution] = []
        self.simulations: list[SavedPacSimulation] = []
        self.trend_markers: dict[tuple[str, str], TrendArrow] = {}
        self.trend_labels: list[tk.Label] = []
        self.trend_overlay_after_id: str | None = None

        header = ctk.CTkFrame(self, fg_color="transparent")
        header.grid(row=0, column=0, columnspan=2, sticky="ew", padx=18, pady=(18, 10))
        header.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(header, text="Esecuzioni PAC", font=ctk.CTkFont(size=24, weight="bold")).grid(
            row=0,
            column=0,
            sticky="w",
        )
        ctk.CTkButton(header, text="Genera dovute", command=self.generate_due).grid(row=0, column=1, padx=6)
        ctk.CTkButton(
            header,
            text="Elimina",
            fg_color="#B91C1C",
            hover_color="#991B1B",
            command=self.delete_selected,
        ).grid(row=0, column=2, padx=(6, 0))

        table_frame = ctk.CTkFrame(self, corner_radius=6)
        table_frame.grid(row=1, column=0, sticky="nsew", padx=(18, 8), pady=(0, 18))
        table_frame.grid_rowconfigure(0, weight=1)
        table_frame.grid_columnconfigure(0, weight=1)
        self.tree = ttk.Treeview(
            table_frame,
            columns=("date", "pac", "amount", "share_price", "shares", "price", "diff", "diff_pct"),
            show="tree headings",
            selectmode="browse",
        )
        configure_treeview_theme(self.tree, "PacExecutions.Treeview")
        self.tree.heading("#0", text="Esecuzione / ETF")
        self.tree.heading("date", text="Data")
        self.tree.heading("pac", text="PAC / ISIN")
        self.tree.heading("amount", text="Investito")
        self.tree.heading("share_price", text="Share price")
        self.tree.heading("shares", text="Shares")
        self.tree.heading("price", text="Prezzo ref.")
        self.tree.heading("diff", text="Diff")
        self.tree.heading("diff_pct", text="Diff %")
        self.tree.column("#0", width=340, minwidth=220)
        self.tree.column("date", width=100, minwidth=90)
        self.tree.column("pac", width=190, minwidth=130)
        self.tree.column("amount", width=110, minwidth=90)
        self.tree.column("share_price", width=100, minwidth=90)
        self.tree.column("shares", width=100, minwidth=90)
        self.tree.column("price", width=100, minwidth=90)
        self.tree.column("diff", width=100, minwidth=90)
        self.tree.column("diff_pct", width=80, minwidth=70)
        self.tree.bind("<<TreeviewSelect>>", lambda _: self.load_selected())
        y_scroll = ttk.Scrollbar(table_frame, orient="vertical", command=self._scroll_tree_y)
        x_scroll = ttk.Scrollbar(table_frame, orient="horizontal", command=self._scroll_tree_x)
        self.y_scroll = y_scroll
        self.x_scroll = x_scroll
        self.tree.configure(yscrollcommand=self._set_y_scroll, xscrollcommand=self._set_x_scroll)
        for event in ("<Configure>", "<<TreeviewOpen>>", "<<TreeviewClose>>", "<MouseWheel>", "<ButtonRelease-1>", "<KeyRelease>"):
            self.tree.bind(event, lambda _event: self._schedule_trend_overlay_refresh(), add="+")
        self.tree.grid(row=0, column=0, sticky="nsew")
        y_scroll.grid(row=0, column=1, sticky="ns")
        x_scroll.grid(row=1, column=0, sticky="ew")

        editor = ctk.CTkFrame(self, corner_radius=6)
        editor.grid(row=1, column=1, sticky="nsew", padx=(8, 18), pady=(0, 18))
        editor.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(editor, text="Esecuzione manuale", font=ctk.CTkFont(size=16, weight="bold")).grid(
            row=0,
            column=0,
            columnspan=2,
            sticky="w",
            padx=14,
            pady=(14, 8),
        )
        ctk.CTkLabel(editor, text="PAC").grid(row=1, column=0, sticky="w", padx=14, pady=6)
        self.simulation_combo = ctk.CTkComboBox(editor, values=["-"], state="readonly")
        self.simulation_combo.grid(row=1, column=1, sticky="ew", padx=(6, 14), pady=6)
        self.date_entry = _entry(editor, "Data", 2)
        self.name_entry = _entry(editor, "Nome", 3)
        ctk.CTkButton(editor, text="Crea/aggiorna manuale", command=self.create_manual).grid(
            row=4,
            column=0,
            columnspan=2,
            sticky="ew",
            padx=14,
            pady=(12, 6),
        )
        ctk.CTkButton(editor, text="Salva nome", command=self.save_selected_name).grid(
            row=5,
            column=0,
            columnspan=2,
            sticky="ew",
            padx=14,
            pady=6,
        )

        ctk.CTkLabel(editor, text="Importo ETF", font=ctk.CTkFont(size=16, weight="bold")).grid(
            row=6,
            column=0,
            columnspan=2,
            sticky="w",
            padx=14,
            pady=(18, 8),
        )
        self.selected_label = ctk.CTkLabel(editor, text="Seleziona una riga ETF", anchor="w", wraplength=280)
        self.selected_label.grid(row=7, column=0, columnspan=2, sticky="ew", padx=14, pady=(0, 8))
        self.amount_entry = _entry(editor, "Investito", 8)
        self.share_price_entry = _entry(editor, "Share price", 9)
        self.shares_entry = _entry(editor, "Shares", 10)
        ctk.CTkButton(editor, text="Salva dettagli ETF", command=self.save_selected_amount).grid(
            row=11,
            column=0,
            columnspan=2,
            sticky="ew",
            padx=14,
            pady=(12, 14),
        )

        self.grid_columnconfigure(0, weight=1)
        self.grid_columnconfigure(1, weight=0)
        self.grid_rowconfigure(1, weight=1)

    def refresh(self) -> None:
        self.simulations = self.context.saved_pac_simulations()
        self.executions = self.context.pac_executions()
        self._refresh_simulation_combo()
        self._render_tree()

    def generate_due(self) -> None:
        try:
            created = self.context.ensure_due_pac_executions()
        except Exception as exc:
            messagebox.showerror("Esecuzioni PAC", str(exc) or exc.__class__.__name__)
            return
        self.refresh()
        messagebox.showinfo("Esecuzioni PAC", f"Esecuzioni create: {len(created)}.")

    def create_manual(self) -> None:
        simulation_id = self._selected_simulation_id()
        if simulation_id is None:
            messagebox.showinfo("Esecuzioni PAC", "Seleziona prima un PAC.")
            return
        try:
            execution_date = _parse_date(self.date_entry.get())
        except ValueError:
            messagebox.showerror("Esecuzioni PAC", "Inserisci una data valida nel formato gg/mm/aaaa.")
            return
        try:
            execution = self.context.create_manual_pac_execution(
                simulation_id,
                execution_date,
                self.name_entry.get(),
            )
        except Exception as exc:
            messagebox.showerror("Esecuzioni PAC", str(exc) or exc.__class__.__name__)
            return
        self.refresh()
        self._select_execution(execution.id)

    def save_selected_name(self) -> None:
        execution = self._selected_execution()
        if execution is None:
            messagebox.showinfo("Esecuzioni PAC", "Seleziona prima una esecuzione.")
            return
        self.context.update_pac_execution_name(execution.id, self.name_entry.get())
        self.refresh()
        self._select_execution(execution.id)

    def save_selected_amount(self) -> None:
        row = self._selected_row()
        if row is None:
            messagebox.showinfo("Esecuzioni PAC", "Seleziona prima una riga ETF.")
            return
        try:
            invested_amount = parse_decimal(self.amount_entry.get())
            share_price, shares = _share_details(
                self.share_price_entry.get(),
                self.shares_entry.get(),
            )
        except ValueError:
            messagebox.showerror(
                "Esecuzioni PAC",
                "Inserisci importo, share price e shares validi. Share price e shares vanno compilati insieme.",
            )
            return

        execution = self.context.update_pac_execution_row_details(
            row.id,
            invested_amount,
            share_price,
            shares,
        )

        row_item_id = f"execrow-{row.id}"

        self.refresh()

        if self.tree.exists(row_item_id):
            parent_id = self.tree.parent(row_item_id)
            grandparent_id = self.tree.parent(parent_id)

            if grandparent_id:
                self.tree.item(grandparent_id, open=True)
            if parent_id:
                self.tree.item(parent_id, open=True)

            self.tree.selection_set(row_item_id)
            self.tree.focus(row_item_id)
            self.tree.see(row_item_id)
        else:
            self._select_execution(execution.id)


    def delete_selected(self) -> None:
        execution = self._selected_execution()
        if execution is None:
            messagebox.showinfo("Esecuzioni PAC", "Seleziona prima una esecuzione.")
            return
        confirmed = messagebox.askyesno("Esecuzioni PAC", f"Eliminare '{execution.name}'?")
        if not confirmed:
            return
        self.context.delete_pac_execution(execution.id)
        self.refresh()

    def load_selected(self) -> None:
        execution = self._selected_execution()
        if execution is not None:
            _replace(self.name_entry, execution.name)
            _replace(self.date_entry, date_text(execution.execution_date))
            self._set_simulation_combo(execution.simulation_id)

        row = self._selected_row()
        if row is None:
            self.selected_label.configure(text="Seleziona una riga ETF")
            _replace(self.amount_entry, "")
            _replace(self.share_price_entry, "")
            _replace(self.shares_entry, "")
            return
        self.selected_label.configure(text=f"{row.name}\n{row.isin}")
        _replace(self.amount_entry, f"{row.invested_amount:.2f}")
        _replace(self.share_price_entry, _decimal_text(row.share_price, 4))
        _replace(self.shares_entry, _decimal_text(row.shares, 6))

    def _render_tree(self) -> None:
        self.tree.delete(*self.tree.get_children())
        self.trend_markers.clear()
        self._clear_trend_labels()
        configure_treeview_tags(self.tree)
        for execution in self.executions:
            execution_id = f"exec-{execution.id}"
            self.tree.insert(
                "",
                "end",
                iid=execution_id,
                text=execution.name,
                values=(
                    date_text(execution.execution_date),
                    execution.simulation_name,
                    money(execution.total_invested),
                    "",
                    "",
                    "",
                    execution.execution_schedule,
                    "manuale" if execution.manual else "auto",
                ),
                tags=("simulation",),
                open=False,
            )
            for item in execution_tree_items(execution):
                self.tree.insert(
                    item.parent_id,
                    "end",
                    iid=item.item_id,
                    text=item.text,
                    values=item.values,
                    tags=(item.tag,),
                    open=item.open,
                )
                for column, arrow in item.trends:
                    self.trend_markers[(item.item_id, column)] = arrow
        self._schedule_trend_overlay_refresh()

    def _scroll_tree_y(self, *args) -> None:
        self.tree.yview(*args)
        self._schedule_trend_overlay_refresh()

    def _scroll_tree_x(self, *args) -> None:
        self.tree.xview(*args)
        self._schedule_trend_overlay_refresh()

    def _set_y_scroll(self, *args) -> None:
        self.y_scroll.set(*args)
        self._schedule_trend_overlay_refresh()

    def _set_x_scroll(self, *args) -> None:
        self.x_scroll.set(*args)
        self._schedule_trend_overlay_refresh()

    def _schedule_trend_overlay_refresh(self) -> None:
        if self.trend_overlay_after_id is not None:
            return
        self.trend_overlay_after_id = self.after_idle(self._refresh_trend_overlays)

    def _refresh_trend_overlays(self) -> None:
        self.trend_overlay_after_id = None
        self._clear_trend_labels()
        for (item_id, column), arrow in self.trend_markers.items():
            if not self.tree.exists(item_id):
                continue
            bbox = self.tree.bbox(item_id, column)
            if not bbox:
                continue
            x, y, _width, height = bbox
            label = tk.Label(
                self.tree,
                text=arrow.arrow,
                fg=arrow.color,
                bg=trend_label_background(
                    tuple(self.tree.item(item_id, "tags")),
                    selected=item_id in self.tree.selection(),
                ),
                borderwidth=0,
                padx=0,
                pady=0,
                font=("Segoe UI", 9, "bold"),
            )
            label.place(x=x + 4, y=y + 1, width=16, height=max(1, height - 2))
            self.trend_labels.append(label)

    def _clear_trend_labels(self) -> None:
        for label in self.trend_labels:
            label.destroy()
        self.trend_labels.clear()

    def _refresh_simulation_combo(self) -> None:
        values = [_simulation_combo_value(simulation) for simulation in self.simulations]
        if not values:
            values = ["-"]
        self.simulation_combo.configure(values=values)
        current = self.simulation_combo.get()
        if current not in values:
            self.simulation_combo.set(values[0])

    def _selected_execution(self) -> PacExecution | None:
        selection = self.tree.selection()
        if not selection:
            return None
        item_id = selection[0]
        if item_id.startswith("execrow-"):
            item_id = self.tree.parent(item_id)
        if "-asset-" in item_id:
            item_id = self.tree.parent(item_id)
        if not item_id.startswith("exec-"):
            return None
        try:
            execution_id = int(item_id.removeprefix("exec-"))
        except ValueError:
            return None
        return next((execution for execution in self.executions if execution.id == execution_id), None)

    def _selected_row(self) -> PacExecutionRow | None:
        selection = self.tree.selection()
        if not selection or not selection[0].startswith("execrow-"):
            return None
        try:
            row_id = int(selection[0].removeprefix("execrow-"))
        except ValueError:
            return None
        for execution in self.executions:
            row = next((item for item in execution.rows if item.id == row_id), None)
            if row is not None:
                return row
        return None

    def _selected_simulation_id(self) -> int | None:
        value = self.simulation_combo.get()
        try:
            return int(value.split(" - ", 1)[0])
        except ValueError:
            return None

    def _set_simulation_combo(self, simulation_id: int | None) -> None:
        if simulation_id is None:
            return
        for simulation in self.simulations:
            if simulation.id == simulation_id:
                self.simulation_combo.set(_simulation_combo_value(simulation))
                return

    def _select_execution(self, execution_id: int) -> None:
        item_id = f"exec-{execution_id}"
        if self.tree.exists(item_id):
            self.tree.selection_set(item_id)
            self.tree.focus(item_id)
            self.tree.see(item_id)


def _entry(master, label: str, row: int) -> ctk.CTkEntry:
    ctk.CTkLabel(master, text=label).grid(row=row, column=0, sticky="w", padx=14, pady=6)
    entry = ctk.CTkEntry(master)
    entry.grid(row=row, column=1, sticky="ew", padx=(6, 14), pady=6)
    return entry


def _replace(entry: ctk.CTkEntry, value: str) -> None:
    entry.delete(0, "end")
    entry.insert(0, value.replace(".", ","))


def _decimal_text(value: float | None, digits: int) -> str:
    if value is None:
        return ""
    return f"{value:.{digits}f}"


def _optional_decimal(text: str) -> float | None:
    if not text.strip():
        return None
    return parse_decimal(text)


def _share_details(share_price_text: str, shares_text: str) -> tuple[float | None, float | None]:
    share_price = _optional_decimal(share_price_text)
    shares = _optional_decimal(shares_text)
    if (share_price is None) != (shares is None):
        raise ValueError("share details incomplete")
    if share_price is not None and (share_price <= 0 or shares is None or shares <= 0):
        raise ValueError("share details invalid")
    return share_price, shares


def _parse_date(text: str) -> date:
    cleaned = text.strip()
    for fmt in ("%d/%m/%Y", "%Y-%m-%d"):
        try:
            from datetime import datetime

            return datetime.strptime(cleaned, fmt).date()
        except ValueError:
            continue
    raise ValueError(cleaned)


def _simulation_combo_value(simulation: SavedPacSimulation) -> str:
    return f"{simulation.id} - {simulation.name}"


def execution_tree_items(execution: PacExecution) -> list[ExecutionTreeItem]:
    items: list[ExecutionTreeItem] = []
    rows_by_asset: dict[str, list[PacExecutionRow]] = defaultdict(list)
    for row in execution.rows:
        rows_by_asset[row.asset_class].append(row)

    for asset_class in ("Azioni", "Obbligazioni", "Alternativi"):
        rows = rows_by_asset.get(asset_class, [])
        if not rows:
            continue
        asset_id = f"exec-{execution.id}-asset-{asset_class}"
        total = sum(row.invested_amount for row in rows)
        items.append(
            ExecutionTreeItem(
                item_id=asset_id,
                parent_id=f"exec-{execution.id}",
                text=asset_class,
                values=("", "", money(total), "", "", "", "", ""),
                tag=asset_class_tag(asset_class),
                open=True,
            )
        )
        for row in rows:
            items.append(
                ExecutionTreeItem(
                    item_id=f"execrow-{row.id}",
                    parent_id=asset_id,
                    text=execution_row_text(row),
                    values=(
                        date_text(row.current_price_date),
                        row.isin,
                        money(row.invested_amount),
                        number(row.share_price, 4),
                        number(row.shares, 6),
                        money(row.current_price),
                        trend_cell_text(row.price_diff, trend_money),
                        trend_cell_text(row.price_diff_pct, trend_pct),
                    ),
                    tag=execution_row_tag(row),
                    trends=trend_columns(row.price_diff, row.price_diff_pct),
                )
            )
    if execution.rows:
        items.append(
            ExecutionTreeItem(
                item_id=f"exec-{execution.id}-total",
                parent_id=f"exec-{execution.id}",
                text="TOTALE",
                values=("", "", money(execution.total_invested), "", "", "", "", ""),
                tag=asset_class_tag("TOTALE"),
            )
        )
    return items


def execution_row_text(row: PacExecutionRow) -> str:
    if row.has_share_details:
        return row.segment
    return f"⚠ {row.segment}"


def execution_row_tag(row: PacExecutionRow) -> str:
    return "etf_row" if row.has_share_details else "warning_row"


def trend_columns(price_diff: float | None, price_diff_pct: float | None) -> tuple[tuple[str, TrendArrow], ...]:
    columns: list[tuple[str, TrendArrow]] = []
    price_arrow = trend_arrow(price_diff)
    pct_arrow = trend_arrow(price_diff_pct)
    if price_arrow is not None:
        columns.append(("diff", price_arrow))
    if pct_arrow is not None:
        columns.append(("diff_pct", pct_arrow))
    return tuple(columns)


def trend_arrow(value: float | None) -> TrendArrow | None:
    if value is None or value == 0:
        return None
    if value > 0:
        return TrendArrow("▲", TREND_UP_COLOR)
    return TrendArrow("▼", TREND_DOWN_COLOR)


def trend_cell_text(value: float | None, formatter) -> str:
    text = formatter(value)
    return f"      {text}" if trend_arrow(value) is not None else text


def trend_label_background(
    tags: tuple[str, ...],
    selected: bool,
    appearance_mode: str | None = None,
) -> str:
    palette = treeview_palette(appearance_mode)
    if selected:
        return palette.selected_background
    tag_colors = treeview_tag_colors(appearance_mode)
    for tag in tags:
        if tag in tag_colors:
            return tag_colors[tag][0]
    return palette.background


def trend_money(value: float | None) -> str:
    if value is None:
        return "-"
    if value > 0:
        return f"+{money(value)}"
    return money(value)


def trend_pct(value: float | None) -> str:
    if value is None:
        return "-"
    if value > 0:
        return f"+{pct(value)}"
    return pct(value)
