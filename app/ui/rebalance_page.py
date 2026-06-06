from __future__ import annotations

from tkinter import messagebox

import customtkinter as ctk

from app.app_context import AppContext
from app.services.rebalance_service import RebalanceMode
from app.ui.widgets import DataTable
from app.utils.formatting import money, number, parse_decimal, pct


class RebalancePage(ctk.CTkFrame):
    def __init__(self, master, context: AppContext):
        super().__init__(master, fg_color="transparent")
        self.context = context

        ctk.CTkLabel(self, text="Ribilanciamento PAC", font=ctk.CTkFont(size=24, weight="bold")).grid(row=0, column=0, sticky="w", padx=18, pady=(18, 10), columnspan=4)
        ctk.CTkLabel(self, text="PAC disponibile").grid(row=1, column=0, sticky="w", padx=(18, 6), pady=8)
        self.pac_entry = ctk.CTkEntry(self, width=120)
        self.pac_entry.grid(row=1, column=1, sticky="w", padx=6, pady=8)
        ctk.CTkLabel(self, text="Modalita").grid(row=1, column=2, sticky="w", padx=(18, 6), pady=8)
        self.mode = ctk.CTkComboBox(self, values=[mode.value for mode in RebalanceMode], width=250)
        self.mode.grid(row=1, column=3, sticky="w", padx=6, pady=8)
        self.mode.set(RebalanceMode.ONLY_UNDERWEIGHT.value)
        ctk.CTkButton(self, text="Calcola", command=self.calculate).grid(row=1, column=4, sticky="w", padx=12, pady=8)

        self.table = DataTable(
            self,
            [
                ("name", "ETF", 300),
                ("target", "Target", 80),
                ("weight", "Peso", 80),
                ("drift_eur", "Scost. EUR", 110),
                ("drift_pct", "Scost. %", 90),
                ("buy", "Compra", 110),
                ("units", "Quote stimate", 120),
            ],
        )
        self.table.grid(row=2, column=0, columnspan=5, sticky="nsew", padx=18, pady=(10, 18))
        self.grid_rowconfigure(2, weight=1)
        self.grid_columnconfigure(4, weight=1)

    def refresh(self) -> None:
        _replace(self.pac_entry, str(self.context.monthly_pac()).replace(".", ","))
        self.calculate()

    def calculate(self) -> None:
        try:
            pac = parse_decimal(self.pac_entry.get())
            mode = RebalanceMode(self.mode.get())
        except ValueError:
            messagebox.showerror("Ribilanciamento", "PAC o modalita non validi.")
            return
        rows = self.context.rebalance_rows(pac, mode)
        self.table.set_rows(
            [
                (
                    str(row.position.etf_id),
                    [
                        row.position.name,
                        pct(row.target_pct),
                        pct(row.current_weight),
                        money(row.drift_value),
                        pct(row.drift_pct),
                        money(row.buy_amount),
                        number(row.estimated_units, 6),
                    ],
                )
                for row in rows
            ]
        )


def _replace(entry: ctk.CTkEntry, value: str) -> None:
    entry.delete(0, "end")
    entry.insert(0, value)
