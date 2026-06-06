from __future__ import annotations

import tkinter as tk
from tkinter import ttk

import customtkinter as ctk


class DataTable(ctk.CTkFrame):
    def __init__(self, master, columns: list[tuple[str, str, int]], **kwargs):
        super().__init__(master, corner_radius=6, **kwargs)
        self.columns = [key for key, _, _ in columns]
        self.tree = ttk.Treeview(self, columns=self.columns, show="headings", selectmode="browse")

        for key, label, width in columns:
            self.tree.heading(key, text=label)
            self.tree.column(key, width=width, minwidth=max(60, min(width, 180)), anchor=tk.W)

        y_scroll = ttk.Scrollbar(self, orient="vertical", command=self.tree.yview)
        x_scroll = ttk.Scrollbar(self, orient="horizontal", command=self.tree.xview)
        self.tree.configure(yscrollcommand=y_scroll.set, xscrollcommand=x_scroll.set)

        self.tree.grid(row=0, column=0, sticky="nsew")
        y_scroll.grid(row=0, column=1, sticky="ns")
        x_scroll.grid(row=1, column=0, sticky="ew")
        self.grid_rowconfigure(0, weight=1)
        self.grid_columnconfigure(0, weight=1)

    def set_rows(self, rows: list[tuple[str, list[str]]]) -> None:
        self.tree.delete(*self.tree.get_children())
        for item_id, values in rows:
            self.tree.insert("", "end", iid=str(item_id), values=values)

    def selected_id(self) -> int | None:
        selection = self.tree.selection()
        if not selection:
            return None
        return int(selection[0])


class KpiBlock(ctk.CTkFrame):
    def __init__(self, master, title: str, value: str = "-", **kwargs):
        super().__init__(master, corner_radius=6, **kwargs)
        self.title_label = ctk.CTkLabel(self, text=title, anchor="w", font=ctk.CTkFont(size=12))
        self.value_label = ctk.CTkLabel(
            self,
            text=value,
            anchor="w",
            font=ctk.CTkFont(size=20, weight="bold"),
        )
        self.title_label.grid(row=0, column=0, sticky="ew", padx=12, pady=(10, 0))
        self.value_label.grid(row=1, column=0, sticky="ew", padx=12, pady=(0, 10))
        self.grid_columnconfigure(0, weight=1)

    def set_value(self, value: str) -> None:
        self.value_label.configure(text=value)
