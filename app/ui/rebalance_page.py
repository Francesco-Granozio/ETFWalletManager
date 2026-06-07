from __future__ import annotations

from tkinter import messagebox

import customtkinter as ctk

from app.app_context import AppContext
from app.domain import RebalancePlan, SavedPacSimulation
from app.services.rebalance_service import RebalanceMode
from app.ui.widgets import DataTable, KpiBlock
from app.utils.formatting import date_text, money, number, pct

ACTION_OPTIONS = ("Auto", "Includi", "Escludi")
ACTION_TO_OVERRIDE = {
    "Auto": "auto",
    "Includi": "include",
    "Escludi": "exclude",
}
OVERRIDE_TO_ACTION = {value: key for key, value in ACTION_TO_OVERRIDE.items()}


class RebalancePage(ctk.CTkFrame):
    def __init__(self, master, context: AppContext):
        super().__init__(master, fg_color="transparent")
        self.context = context
        self.simulations: list[SavedPacSimulation] = []
        self.simulation_values: dict[str, int] = {}
        self.overrides: dict[str, str] = {}
        self.current_plan: RebalancePlan | None = None

        header = ctk.CTkFrame(self, fg_color="transparent")
        header.grid(row=0, column=0, sticky="ew", padx=18, pady=(18, 10), columnspan=4)
        header.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(header, text="Ribilanciamento PAC", font=ctk.CTkFont(size=24, weight="bold")).grid(
            row=0,
            column=0,
            sticky="w",
        )
        ctk.CTkButton(header, text="Ricarica", command=self.refresh).grid(row=0, column=1, sticky="e")

        controls = ctk.CTkFrame(self, corner_radius=6)
        controls.grid(row=1, column=0, columnspan=4, sticky="ew", padx=18, pady=(0, 8))
        controls.grid_columnconfigure(1, weight=1)
        controls.grid_columnconfigure(3, weight=1)
        ctk.CTkLabel(controls, text="PAC").grid(row=0, column=0, sticky="w", padx=(14, 6), pady=12)
        self.simulation_combo = ctk.CTkComboBox(controls, values=["-"], state="readonly", command=lambda _: self.calculate())
        self.simulation_combo.grid(row=0, column=1, sticky="ew", padx=6, pady=12)
        ctk.CTkLabel(controls, text="Strategia").grid(row=0, column=2, sticky="w", padx=(18, 6), pady=12)
        self.mode_combo = ctk.CTkComboBox(
            controls,
            values=[mode.value for mode in RebalanceMode],
            state="readonly",
            command=lambda _: self.calculate(),
        )
        self.mode_combo.grid(row=0, column=3, sticky="ew", padx=6, pady=12)
        self.mode_combo.set(RebalanceMode.ONLY_UNDERWEIGHT.value)
        ctk.CTkButton(controls, text="Calcola", command=self.calculate).grid(row=0, column=4, padx=(12, 14), pady=12)

        self.total_value = KpiBlock(self, "Valore snapshot")
        self.budget = KpiBlock(self, "Budget PAC")
        self.underweight = KpiBlock(self, "Sottopesati")
        self.overweight = KpiBlock(self, "Sovrappesati")
        for index, block in enumerate((self.total_value, self.budget, self.underweight, self.overweight)):
            block.grid(
                row=2,
                column=index,
                sticky="nsew",
                padx=(18 if index == 0 else 8, 18 if index == 3 else 8),
                pady=8,
            )
            self.grid_columnconfigure(index, weight=1)

        self.meta = ctk.CTkLabel(self, text="", anchor="w")
        self.meta.grid(row=3, column=0, columnspan=4, sticky="ew", padx=18, pady=(4, 8))

        self.table = DataTable(
            self,
            [
                ("asset", "Asset", 120),
                ("status", "Stato", 120),
                ("action", "Azione", 90),
                ("target", "Target", 80),
                ("weight", "Peso", 80),
                ("drift_eur", "Scost. EUR", 110),
                ("drift_pct", "Scost. %", 90),
                ("buy", "Compra", 110),
                ("units", "Quote stimate", 120),
                ("name", "Strumento", 260),
                ("isin", "ISIN", 130),
            ],
        )
        self.table.grid(row=4, column=0, columnspan=3, sticky="nsew", padx=(18, 8), pady=(8, 18))
        self.table.tree.bind("<<TreeviewSelect>>", lambda _: self._load_selected_override())

        side = ctk.CTkFrame(self, corner_radius=6)
        side.grid(row=4, column=3, sticky="nsew", padx=(8, 18), pady=(8, 18))
        side.grid_columnconfigure(0, weight=1)
        side.grid_rowconfigure(5, weight=1)
        ctk.CTkLabel(side, text="Override ETF", font=ctk.CTkFont(size=16, weight="bold")).grid(
            row=0,
            column=0,
            sticky="w",
            padx=14,
            pady=(14, 6),
        )
        self.selected_label = ctk.CTkLabel(side, text="Nessuna riga selezionata", anchor="w", wraplength=280)
        self.selected_label.grid(row=1, column=0, sticky="ew", padx=14, pady=(0, 8))
        self.action_combo = ctk.CTkComboBox(side, values=list(ACTION_OPTIONS), state="readonly")
        self.action_combo.grid(row=2, column=0, sticky="ew", padx=14, pady=6)
        self.action_combo.set("Auto")
        ctk.CTkButton(side, text="Applica override", command=self.apply_override).grid(
            row=3,
            column=0,
            sticky="ew",
            padx=14,
            pady=(6, 14),
        )
        ctk.CTkLabel(side, text="Strategia proposta", font=ctk.CTkFont(size=16, weight="bold")).grid(
            row=4,
            column=0,
            sticky="w",
            padx=14,
            pady=(8, 6),
        )
        self.strategy_text = ctk.CTkTextbox(side, height=280, wrap="word")
        self.strategy_text.grid(row=5, column=0, sticky="nsew", padx=14, pady=(0, 14))
        self.strategy_text.configure(state="disabled")

        self.grid_rowconfigure(4, weight=1)

    def refresh(self) -> None:
        previous_id = self._selected_simulation_id()
        self.simulations = self.context.saved_pac_simulations()
        values = [_simulation_combo_value(simulation) for simulation in self.simulations]
        self.simulation_values = {
            _simulation_combo_value(simulation): simulation.id
            for simulation in self.simulations
        }
        if not values:
            values = ["-"]
        self.simulation_combo.configure(values=values)
        selected_value = next(
            (
                value
                for value, simulation_id in self.simulation_values.items()
                if simulation_id == previous_id
            ),
            values[0],
        )
        self.simulation_combo.set(selected_value)
        self.calculate()

    def calculate(self) -> None:
        simulation_id = self._selected_simulation_id()
        if simulation_id is None:
            self.current_plan = None
            self._render_empty("Nessun PAC salvato disponibile.")
            return
        try:
            plan = self.context.rebalance_plan_for_simulation(
                simulation_id,
                RebalanceMode(self.mode_combo.get()),
                overrides=self.overrides,
            )
        except ValueError as exc:
            self.current_plan = None
            self._render_empty(str(exc))
            return
        except Exception as exc:
            messagebox.showerror("Ribilanciamento", str(exc) or exc.__class__.__name__)
            return
        self.current_plan = plan
        self._render_plan(plan)

    def apply_override(self) -> None:
        isin = self._selected_isin()
        if isin is None:
            messagebox.showinfo("Ribilanciamento", "Seleziona prima una riga ETF.")
            return
        selected = ACTION_TO_OVERRIDE.get(self.action_combo.get(), "auto")
        if selected == "auto":
            self.overrides.pop(isin, None)
        else:
            self.overrides[isin] = selected
        self.calculate()
        self._select_isin(isin)

    def _render_plan(self, plan: RebalancePlan) -> None:
        self.total_value.set_value(money(plan.total_current_value))
        self.budget.set_value(money(plan.budget))
        self.underweight.set_value(str(plan.underweight_count))
        self.overweight.set_value(str(plan.overweight_count))
        snapshot_text = (
            f"Snapshot LS: {date_text(plan.latest_live_price_date)}"
            if plan.latest_live_price_date is not None
            else "Snapshot LS: senza data prezzi"
        )
        self.meta.configure(text=f"PAC: {plan.simulation_name} | {snapshot_text} | ETF: {len(plan.rows)}")
        self.table.set_rows(rebalance_table_rows(plan))
        self._set_strategy_text(strategy_text(plan))
        self._load_selected_override()

    def _render_empty(self, message: str) -> None:
        self.total_value.set_value("-")
        self.budget.set_value("-")
        self.underweight.set_value("-")
        self.overweight.set_value("-")
        self.meta.configure(text=message)
        self.table.set_rows([])
        self._set_strategy_text(message)
        self.selected_label.configure(text="Nessuna riga selezionata")
        self.action_combo.set("Auto")

    def _set_strategy_text(self, text: str) -> None:
        self.strategy_text.configure(state="normal")
        self.strategy_text.delete("1.0", "end")
        self.strategy_text.insert("1.0", text)
        self.strategy_text.configure(state="disabled")

    def _load_selected_override(self) -> None:
        isin = self._selected_isin()
        if isin is None:
            self.selected_label.configure(text="Nessuna riga selezionata")
            self.action_combo.set("Auto")
            return
        row = self._plan_row(isin)
        self.selected_label.configure(text=f"{row.name}\n{isin}" if row else isin)
        self.action_combo.set(OVERRIDE_TO_ACTION.get(self.overrides.get(isin, "auto"), "Auto"))

    def _selected_simulation_id(self) -> int | None:
        return self.simulation_values.get(self.simulation_combo.get())

    def _selected_isin(self) -> str | None:
        selection = self.table.tree.selection()
        if not selection:
            return None
        item_id = selection[0]
        if not item_id.startswith("isin-"):
            return None
        return item_id.removeprefix("isin-")

    def _select_isin(self, isin: str) -> None:
        item_id = f"isin-{isin}"
        if self.table.tree.exists(item_id):
            self.table.tree.selection_set(item_id)
            self.table.tree.focus(item_id)
            self.table.tree.see(item_id)

    def _plan_row(self, isin: str):
        if self.current_plan is None:
            return None
        return next((row for row in self.current_plan.rows if row.isin == isin), None)


def rebalance_table_rows(plan: RebalancePlan) -> list[tuple[str, list[str], str]]:
    return [
        (
            f"isin-{row.isin}",
            [
                row.asset_class,
                row.status,
                row.action,
                pct(row.target_pct),
                pct(row.current_weight),
                _signed_money(row.drift_value),
                _signed_pct(row.drift_pct),
                money(row.buy_amount),
                number(row.estimated_units, 6),
                row.name,
                row.isin,
            ],
            _row_tag(row.status),
        )
        for row in plan.rows
    ]


def strategy_text(plan: RebalancePlan) -> str:
    lines = [
        f"Budget: {money(plan.budget)}",
        f"Valore snapshot: {money(plan.total_current_value)}",
        "",
    ]
    if not plan.operations:
        lines.append("Nessun acquisto suggerito con le opzioni selezionate.")
    else:
        lines.append("Acquisti suggeriti:")
        for operation in plan.operations:
            units = number(operation.estimated_units, 6)
            lines.append(
                f"- {money(operation.buy_amount)} su {operation.name} ({operation.isin}) | "
                f"quote stimate: {units} | {operation.reason}"
            )
    if plan.warnings:
        lines.extend(["", "Avvisi:"])
        lines.extend(f"- {warning}" for warning in plan.warnings)
    return "\n".join(lines)


def _simulation_combo_value(simulation: SavedPacSimulation) -> str:
    return f"{simulation.id} - {simulation.name}"


def _row_tag(status: str) -> str:
    if status == "Sottopesato":
        return "rebalance_underweight"
    if status == "Sovrappesato":
        return "rebalance_overweight"
    if status == "Non calcolabile":
        return "warning_row"
    return "etf_row"


def _signed_money(value: float | None) -> str:
    if value is None:
        return "-"
    if value > 0:
        return f"+{money(value)}"
    return money(value)


def _signed_pct(value: float | None) -> str:
    if value is None:
        return "-"
    if value > 0:
        return f"+{pct(value)}"
    return pct(value)
