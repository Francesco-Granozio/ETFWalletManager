from __future__ import annotations

from datetime import date
from tkinter import messagebox

import customtkinter as ctk

from app.app_context import AppContext
from app.domain import AllocationSummary
from app.ui.widgets import DataTable
from app.utils.formatting import date_text, money, number, parse_decimal, pct


class AllocationPage(ctk.CTkFrame):
    def __init__(self, master, context: AppContext):
        super().__init__(master, fg_color="transparent")
        self.context = context
        self.summary: AllocationSummary | None = None

        header = ctk.CTkFrame(self, fg_color="transparent")
        header.grid(row=0, column=0, columnspan=2, sticky="ew", padx=18, pady=(18, 10))
        header.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(header, text="Ripartizione", font=ctk.CTkFont(size=24, weight="bold")).grid(row=0, column=0, sticky="w")
        ctk.CTkButton(header, text="Aggiorna prezzi", command=self.update_prices).grid(row=0, column=1, padx=6)
        ctk.CTkButton(header, text="Crea snapshot mese", command=self.create_snapshot).grid(row=0, column=2, padx=6)

        self.info = ctk.CTkLabel(self, text="", anchor="w")
        self.info.grid(row=1, column=0, columnspan=2, sticky="ew", padx=18, pady=(0, 8))

        self.table = DataTable(
            self,
            [
                ("asset", "Asset", 120),
                ("segment", "Segmento", 180),
                ("name", "ETF", 300),
                ("isin", "ISIN", 120),
                ("target", "Target", 80),
                ("qty", "Quote", 90),
                ("price", "Prezzo", 90),
                ("value", "Valore", 120),
                ("weight", "Peso", 80),
                ("drift", "Scost. EUR", 110),
                ("ter", "TER annuo", 110),
            ],
        )
        self.table.grid(row=2, column=0, sticky="nsew", padx=(18, 8), pady=(0, 18))
        self.table.tree.bind("<<TreeviewSelect>>", lambda _: self.load_selected())

        editor = ctk.CTkFrame(self, corner_radius=6)
        editor.grid(row=2, column=1, sticky="nsew", padx=(8, 18), pady=(0, 18))
        ctk.CTkLabel(editor, text="Modifica posizione", font=ctk.CTkFont(size=16, weight="bold")).grid(row=0, column=0, sticky="w", padx=14, pady=(14, 8), columnspan=2)
        self.selected_label = ctk.CTkLabel(editor, text="Seleziona un ETF", anchor="w", wraplength=260)
        self.selected_label.grid(row=1, column=0, columnspan=2, sticky="ew", padx=14, pady=(0, 12))

        self.quantity_entry = _entry(editor, "Quote", 2)
        self.average_entry = _entry(editor, "Prezzo medio", 3)
        self.price_entry = _entry(editor, "Prezzo attuale", 4)
        ctk.CTkButton(editor, text="Salva quote/prezzo", command=self.save_selected).grid(row=5, column=0, columnspan=2, sticky="ew", padx=14, pady=(14, 8))
        editor.grid_columnconfigure(1, weight=1)

        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(2, weight=1)

    def refresh(self) -> None:
        self.summary = self.context.allocation_summary()
        self.info.configure(
            text=(
                f"Valore portafoglio: {money(self.summary.total_value)}  |  "
                f"TER medio: {pct(self.summary.weighted_ter)}  |  "
                f"Ultimo update prezzi: {date_text(self.summary.latest_price_date)}"
            )
        )
        rows = []
        for row in self.summary.rows:
            p = row.position
            rows.append(
                (
                    str(p.etf_id),
                    [
                        p.asset_class,
                        p.segment,
                        p.name,
                        p.isin,
                        pct(p.target_pct),
                        number(p.quantity, 4),
                        money(p.price),
                        money(row.current_value),
                        pct(row.current_weight),
                        money(row.drift_value),
                        money(row.annual_ter_cost),
                    ],
                )
            )
        self.table.set_rows(rows)

    def load_selected(self) -> None:
        position = self._selected_position()
        if not position:
            return
        self.selected_label.configure(text=f"{position.name}\n{position.isin}")
        _replace(self.quantity_entry, number(position.quantity, 6))
        _replace(self.average_entry, number(position.average_price, 4))
        _replace(self.price_entry, number(position.price, 4))

    def save_selected(self) -> None:
        position = self._selected_position()
        if not position:
            messagebox.showinfo("Ripartizione", "Seleziona prima un ETF.")
            return
        try:
            quantity = parse_decimal(self.quantity_entry.get())
            average_price = parse_decimal(self.average_entry.get())
            price = parse_decimal(self.price_entry.get())
        except ValueError:
            messagebox.showerror("Ripartizione", "Inserisci numeri validi.")
            return
        self.context.save_holding(position.etf_id, quantity, average_price)
        self.context.save_manual_price(position.etf_id, price, date.today())
        self.refresh()

    def update_prices(self) -> None:
        results = self.context.update_prices()
        ok_count = sum(1 for result in results if result.ok)
        messagebox.showinfo("Aggiornamento prezzi", f"Aggiornati: {ok_count}/{len(results)}. I fallimenti mantengono il prezzo cached.")
        self.refresh()

    def create_snapshot(self) -> None:
        snapshot = self.context.create_current_month_snapshot()
        messagebox.showinfo("Snapshot", f"Snapshot {date_text(snapshot.date)}: {money(snapshot.total_value)}")

    def _selected_position(self):
        item_id = self.table.selected_id()
        if item_id is None or not self.summary:
            return None
        for row in self.summary.rows:
            if row.position.etf_id == item_id:
                return row.position
        return None


def _entry(master, label: str, row: int) -> ctk.CTkEntry:
    ctk.CTkLabel(master, text=label).grid(row=row, column=0, sticky="w", padx=14, pady=6)
    entry = ctk.CTkEntry(master)
    entry.grid(row=row, column=1, sticky="ew", padx=(4, 14), pady=6)
    return entry


def _replace(entry: ctk.CTkEntry, value: str) -> None:
    entry.delete(0, "end")
    entry.insert(0, value)
