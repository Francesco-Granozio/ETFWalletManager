from __future__ import annotations

from tkinter import messagebox

import customtkinter as ctk

from app.app_context import AppContext
from app.services.rebalance_service import RebalanceMode
from app.utils.formatting import parse_decimal


class SettingsPage(ctk.CTkFrame):
    def __init__(self, master, context: AppContext):
        super().__init__(master, fg_color="transparent")
        self.context = context

        ctk.CTkLabel(self, text="Impostazioni", font=ctk.CTkFont(size=24, weight="bold")).grid(row=0, column=0, sticky="w", padx=18, pady=(18, 16), columnspan=2)

        self.monthly_pac = _entry(self, "PAC mensile", 1)
        self.auto_update = ctk.CTkSwitch(self, text="Aggiornamento automatico")
        self.auto_update.grid(row=2, column=0, columnspan=2, sticky="w", padx=18, pady=8)
        self.auto_snapshot = ctk.CTkSwitch(self, text="Snapshot automatico a inizio mese")
        self.auto_snapshot.grid(row=3, column=0, columnspan=2, sticky="w", padx=18, pady=8)

        self.frequency = _combo(self, "Frequenza aggiornamento", ["daily", "weekly", "startup"], 4)
        self.theme = _combo(self, "Tema", ["dark", "light", "system"], 5)
        self.rebalance_mode = _combo(self, "Modalita ribilanciamento", [mode.value for mode in RebalanceMode], 6)
        self.fallback_price = _combo(self, "Fallback prezzo", ["last_available", "manual"], 7)

        ctk.CTkButton(self, text="Salva impostazioni", command=self.save).grid(row=8, column=0, columnspan=2, sticky="ew", padx=18, pady=(18, 8))
        self.grid_columnconfigure(1, weight=1)

    def refresh(self) -> None:
        settings = self.context.settings()
        _replace(self.monthly_pac, settings.get("monthly_pac", "204"))
        self._set_switch(self.auto_update, settings.get("auto_update_enabled", "false") == "true")
        self._set_switch(self.auto_snapshot, settings.get("auto_snapshot_enabled", "true") == "true")
        self.frequency.set(settings.get("auto_update_frequency", "daily"))
        self.theme.set(settings.get("theme", "dark"))
        self.rebalance_mode.set(settings.get("rebalance_mode", RebalanceMode.ONLY_UNDERWEIGHT.value))
        self.fallback_price.set(settings.get("fallback_price", "last_available"))

    def save(self) -> None:
        try:
            monthly_pac = parse_decimal(self.monthly_pac.get())
        except ValueError:
            messagebox.showerror("Impostazioni", "PAC mensile non valido.")
            return
        values = {
            "monthly_pac": str(monthly_pac),
            "auto_update_enabled": "true" if self.auto_update.get() else "false",
            "auto_snapshot_enabled": "true" if self.auto_snapshot.get() else "false",
            "auto_update_frequency": self.frequency.get(),
            "theme": self.theme.get(),
            "rebalance_mode": self.rebalance_mode.get(),
            "fallback_price": self.fallback_price.get(),
        }
        self.context.save_settings(values)
        ctk.set_appearance_mode(values["theme"])
        messagebox.showinfo("Impostazioni", "Impostazioni salvate.")

    @staticmethod
    def _set_switch(switch: ctk.CTkSwitch, enabled: bool) -> None:
        if enabled:
            switch.select()
        else:
            switch.deselect()


def _entry(master, label: str, row: int) -> ctk.CTkEntry:
    ctk.CTkLabel(master, text=label).grid(row=row, column=0, sticky="w", padx=18, pady=8)
    entry = ctk.CTkEntry(master)
    entry.grid(row=row, column=1, sticky="ew", padx=18, pady=8)
    return entry


def _combo(master, label: str, values: list[str], row: int) -> ctk.CTkComboBox:
    ctk.CTkLabel(master, text=label).grid(row=row, column=0, sticky="w", padx=18, pady=8)
    combo = ctk.CTkComboBox(master, values=values)
    combo.grid(row=row, column=1, sticky="ew", padx=18, pady=8)
    combo.set(values[0])
    return combo


def _replace(entry: ctk.CTkEntry, value: str) -> None:
    entry.delete(0, "end")
    entry.insert(0, value.replace(".", ","))
