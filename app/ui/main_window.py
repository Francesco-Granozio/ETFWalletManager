from __future__ import annotations

import customtkinter as ctk

from app.app_context import AppContext
from app.ui.allocation_page import AllocationPage
from app.ui.dashboard import DashboardPage
from app.ui.pac_simulation_page import PacSimulationPage
from app.ui.performance_page import PerformancePage
from app.ui.rebalance_page import RebalancePage
from app.ui.settings_page import SettingsPage


class MainWindow(ctk.CTk):
    def __init__(self, context: AppContext):
        super().__init__()
        self.context = context
        settings = self.context.settings()
        ctk.set_appearance_mode(settings.get("theme", "dark"))
        ctk.set_default_color_theme("blue")

        self.title("PAC ETF Tracker")
        self.geometry("1280x760")
        self.minsize(1040, 640)

        self.sidebar = ctk.CTkFrame(self, width=210, corner_radius=0)
        self.sidebar.grid(row=0, column=0, sticky="nsew")
        self.sidebar.grid_rowconfigure(8, weight=1)
        ctk.CTkLabel(self.sidebar, text="PAC ETF", font=ctk.CTkFont(size=22, weight="bold")).grid(row=0, column=0, padx=18, pady=(22, 18), sticky="w")

        self.content = ctk.CTkFrame(self, fg_color="transparent")
        self.content.grid(row=0, column=1, sticky="nsew")
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)

        self.pages = {
            "Dashboard": DashboardPage(self.content, context),
            "Simula ripartizione": PacSimulationPage(self.content, context),
            "Ripartizione": AllocationPage(self.content, context),
            "Ribilanciamento": RebalancePage(self.content, context),
            "Performance": PerformancePage(self.content, context),
            "Impostazioni": SettingsPage(self.content, context),
        }
        for page in self.pages.values():
            page.grid(row=0, column=0, sticky="nsew")
        self.content.grid_columnconfigure(0, weight=1)
        self.content.grid_rowconfigure(0, weight=1)

        for index, name in enumerate(self.pages, start=1):
            ctk.CTkButton(self.sidebar, text=name, anchor="w", command=lambda selected=name: self.show_page(selected)).grid(
                row=index,
                column=0,
                sticky="ew",
                padx=14,
                pady=5,
            )

        self.status = ctk.CTkLabel(self.sidebar, text="", anchor="w", wraplength=170)
        self.status.grid(row=9, column=0, sticky="ew", padx=18, pady=(8, 18))

        self.show_page("Dashboard")
        self.after(250, self._startup_tasks)

    def show_page(self, name: str) -> None:
        page = self.pages[name]
        page.tkraise()
        if hasattr(page, "refresh"):
            page.refresh()
        self.status.configure(text=f"Vista: {name}")

    def _startup_tasks(self) -> None:
        settings = self.context.settings()
        if settings.get("auto_snapshot_enabled", "true") == "true":
            self.context.create_current_month_snapshot()
            self.pages["Dashboard"].refresh()
        if settings.get("auto_update_enabled", "false") == "true" and settings.get("auto_update_frequency") == "startup":
            self.context.update_prices()
            self.pages["Dashboard"].refresh()
