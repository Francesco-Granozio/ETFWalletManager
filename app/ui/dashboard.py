from __future__ import annotations

import customtkinter as ctk

from app.app_context import AppContext
from app.utils.formatting import date_text, money, pct
from app.ui.widgets import DataTable, KpiBlock


class DashboardPage(ctk.CTkFrame):
    def __init__(self, master, context: AppContext):
        super().__init__(master, fg_color="transparent")
        self.context = context

        self.title = ctk.CTkLabel(self, text="Dashboard", font=ctk.CTkFont(size=24, weight="bold"))
        self.title.grid(row=0, column=0, sticky="w", padx=18, pady=(18, 10), columnspan=4)

        self.total = KpiBlock(self, "Valore attuale")
        self.month = KpiBlock(self, "Performance mese")
        self.ytd = KpiBlock(self, "Performance YTD")
        self.yoy = KpiBlock(self, "Performance anno")
        for index, block in enumerate((self.total, self.month, self.ytd, self.yoy)):
            block.grid(row=1, column=index, sticky="nsew", padx=(18 if index == 0 else 8, 18 if index == 3 else 8), pady=8)
            self.grid_columnconfigure(index, weight=1)

        self.meta = ctk.CTkLabel(self, text="", anchor="w")
        self.meta.grid(row=2, column=0, columnspan=4, sticky="ew", padx=18, pady=(6, 8))

        self.asset_table = DataTable(
            self,
            [
                ("asset", "Asset class", 180),
                ("target", "Target", 100),
                ("value", "Valore", 140),
                ("weight", "Peso", 100),
                ("drift", "Scost.", 100),
            ],
        )
        self.asset_table.grid(row=3, column=0, columnspan=4, sticky="nsew", padx=18, pady=(8, 18))
        self.grid_rowconfigure(3, weight=1)

    def refresh(self) -> None:
        allocation = self.context.allocation_summary()
        report = self.context.performance_report()
        self.total.set_value(money(allocation.total_value))
        self.month.set_value(_diff_text(report.monthly_diff, report.monthly_diff_pct))
        self.ytd.set_value(_diff_text(report.ytd_diff, report.ytd_diff_pct))
        self.yoy.set_value(_diff_text(report.yearly_diff, report.yearly_diff_pct))
        self.meta.configure(
            text=f"TER medio: {pct(allocation.weighted_ter)}  |  Ultimo update prezzi: {date_text(allocation.latest_price_date)}"
        )
        rows = [
            (
                summary.asset_class,
                [
                    summary.asset_class,
                    pct(summary.target_pct),
                    money(summary.value),
                    pct(summary.current_weight),
                    pct(summary.drift_pct),
                ],
            )
            for summary in allocation.asset_classes.values()
        ]
        self.asset_table.set_rows(rows)


def _diff_text(value: float | None, percent: float | None) -> str:
    if value is None:
        return "-"
    return f"{money(value)} ({pct(percent)})"
