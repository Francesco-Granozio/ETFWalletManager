from __future__ import annotations

import customtkinter as ctk
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from matplotlib.figure import Figure

from app.app_context import AppContext
from app.ui.widgets import DataTable, KpiBlock
from app.utils.formatting import date_text, money, pct


class PerformancePage(ctk.CTkFrame):
    def __init__(self, master, context: AppContext):
        super().__init__(master, fg_color="transparent")
        self.context = context
        self.chart_canvas = None

        header = ctk.CTkFrame(self, fg_color="transparent")
        header.grid(row=0, column=0, columnspan=4, sticky="ew", padx=18, pady=(18, 10))
        header.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(header, text="Performance", font=ctk.CTkFont(size=24, weight="bold")).grid(row=0, column=0, sticky="w")
        ctk.CTkButton(header, text="Crea snapshot mese", command=self.create_snapshot).grid(row=0, column=1, padx=6)

        self.current = KpiBlock(self, "Snapshot corrente")
        self.month = KpiBlock(self, "Differenza mese")
        self.ytd = KpiBlock(self, "Differenza YTD")
        self.yoy = KpiBlock(self, "Differenza anno")
        for index, block in enumerate((self.current, self.month, self.ytd, self.yoy)):
            block.grid(row=1, column=index, sticky="nsew", padx=(18 if index == 0 else 8, 18 if index == 3 else 8), pady=8)
            self.grid_columnconfigure(index, weight=1)

        self.chart_frame = ctk.CTkFrame(self, corner_radius=6)
        self.chart_frame.grid(row=2, column=0, columnspan=4, sticky="nsew", padx=18, pady=8)

        self.table = DataTable(
            self,
            [
                ("date", "Data", 110),
                ("total", "Totale", 140),
                ("equity", "Azioni", 140),
                ("bond", "Bond", 140),
                ("alt", "Alternativi", 140),
            ],
        )
        self.table.grid(row=3, column=0, columnspan=4, sticky="nsew", padx=18, pady=(8, 18))
        self.grid_rowconfigure(2, weight=1)
        self.grid_rowconfigure(3, weight=1)

    def refresh(self) -> None:
        report = self.context.performance_report()
        snapshots = self.context.snapshots()
        self.current.set_value(_snapshot_text(report.current))
        self.month.set_value(_diff_text(report.monthly_diff, report.monthly_diff_pct))
        self.ytd.set_value(_diff_text(report.ytd_diff, report.ytd_diff_pct))
        self.yoy.set_value(_diff_text(report.yearly_diff, report.yearly_diff_pct))
        self.table.set_rows(
            [
                (
                    snapshot.date.isoformat(),
                    [
                        date_text(snapshot.date),
                        money(snapshot.total_value),
                        money(snapshot.equity_value),
                        money(snapshot.bond_value),
                        money(snapshot.alternative_value),
                    ],
                )
                for snapshot in snapshots
            ]
        )
        self._draw_chart(snapshots)

    def create_snapshot(self) -> None:
        self.context.create_current_month_snapshot()
        self.refresh()

    def _draw_chart(self, snapshots) -> None:
        if self.chart_canvas:
            self.chart_canvas.get_tk_widget().destroy()
            self.chart_canvas = None
        fig = Figure(figsize=(7, 2.4), dpi=100)
        ax = fig.add_subplot(111)
        if snapshots:
            ax.plot([snapshot.date for snapshot in snapshots], [snapshot.total_value for snapshot in snapshots], marker="o", color="#2A9D8F")
        ax.set_title("Valore snapshot mensili")
        ax.set_ylabel("EUR")
        ax.grid(True, alpha=0.25)
        fig.tight_layout()
        self.chart_canvas = FigureCanvasTkAgg(fig, master=self.chart_frame)
        self.chart_canvas.draw()
        self.chart_canvas.get_tk_widget().pack(fill="both", expand=True, padx=8, pady=8)


def _snapshot_text(snapshot) -> str:
    if not snapshot:
        return "-"
    return f"{date_text(snapshot.date)} - {money(snapshot.total_value)}"


def _diff_text(value: float | None, percent: float | None) -> str:
    if value is None:
        return "-"
    return f"{money(value)} ({pct(percent)})"
