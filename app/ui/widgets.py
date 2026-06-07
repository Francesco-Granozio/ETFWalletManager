from __future__ import annotations

from dataclasses import dataclass
import tkinter as tk
from tkinter import ttk

import customtkinter as ctk


@dataclass(frozen=True, slots=True)
class TreeviewPalette:
    background: str
    foreground: str
    field_background: str
    heading_background: str
    heading_foreground: str
    selected_background: str
    selected_foreground: str
    border: str


def treeview_palette(appearance_mode: str | None = None) -> TreeviewPalette:
    mode = (appearance_mode or ctk.get_appearance_mode()).lower()
    if mode == "dark":
        return TreeviewPalette(
            background="#111827",
            foreground="#F9FAFB",
            field_background="#111827",
            heading_background="#1F2937",
            heading_foreground="#F9FAFB",
            selected_background="#555080",
            selected_foreground="#FFFFFF",
            border="#374151",
        )
    return TreeviewPalette(
        background="#F9FAFB",
        foreground="#111827",
        field_background="#F9FAFB",
        heading_background="#E5E7EB",
        heading_foreground="#111827",
        selected_background="#2563EB",
        selected_foreground="#FFFFFF",
        border="#D1D5DB",
    )


def asset_class_tag(asset_class: str) -> str:
    normalized = asset_class.strip().lower()
    if normalized == "azioni":
        return "asset_azioni"
    if normalized == "obbligazioni":
        return "asset_obbligazioni"
    if normalized == "alternativi":
        return "asset_alternativi"
    if normalized == "totale":
        return "asset_totale"
    return "asset_unknown"


def configure_treeview_theme(tree: ttk.Treeview, style_name: str = "App.Treeview") -> None:
    palette = treeview_palette()
    style = ttk.Style(tree)
    try:
        style.theme_use("default")
    except tk.TclError:
        pass
    style.configure(
        style_name,
        background=palette.background,
        foreground=palette.foreground,
        fieldbackground=palette.field_background,
        bordercolor=palette.border,
        lightcolor=palette.border,
        darkcolor=palette.border,
        rowheight=24,
    )
    style.configure(
        f"{style_name}.Heading",
        background=palette.heading_background,
        foreground=palette.heading_foreground,
        bordercolor=palette.border,
        relief="flat",
    )
    style.map(
        style_name,
        background=[("selected", palette.selected_background)],
        foreground=[("selected", palette.selected_foreground)],
    )
    for scrollbar_style in ("Vertical.TScrollbar", "Horizontal.TScrollbar"):
        style.configure(
            scrollbar_style,
            background=palette.heading_background,
            troughcolor=palette.background,
            bordercolor=palette.border,
            arrowcolor=palette.foreground,
            lightcolor=palette.border,
            darkcolor=palette.border,
        )
    tree.configure(style=style_name)
    configure_treeview_tags(tree)


def configure_treeview_tags(tree: ttk.Treeview) -> None:
    for tag, (background, foreground) in treeview_tag_colors().items():
        tree.tag_configure(tag, background=background, foreground=foreground)


def treeview_tag_colors(appearance_mode: str | None = None) -> dict[str, tuple[str, str]]:
    dark = (appearance_mode or ctk.get_appearance_mode()).lower() == "dark"
    if dark:
        return {
            "simulation": ("#555080", "#F9FAFB"),
            "asset_azioni": ("#2563EB", "#FFFFFF"),
            "asset_obbligazioni": ("#DC2626", "#FFFFFF"),
            "asset_alternativi": ("#F59E0B", "#111827"),
            "asset_totale": ("#16A34A", "#FFFFFF"),
            "asset_unknown": ("#374151", "#F9FAFB"),
            "warning_row": ("#7F1D1D", "#FEE2E2"),
            "rebalance_underweight": ("#064E3B", "#D1FAE5"),
            "rebalance_overweight": ("#7F1D1D", "#FEE2E2"),
            "etf_row": ("#111827", "#F9FAFB"),
        }
    return {
        "simulation": ("#EFF6FF", "#111827"),
        "asset_azioni": ("#3B82F6", "#111827"),
        "asset_obbligazioni": ("#EF4444", "#111827"),
        "asset_alternativi": ("#FBBF24", "#111827"),
        "asset_totale": ("#6AA84F", "#111827"),
        "asset_unknown": ("#E5E7EB", "#111827"),
        "warning_row": ("#FEE2E2", "#991B1B"),
        "rebalance_underweight": ("#DCFCE7", "#166534"),
        "rebalance_overweight": ("#FEE2E2", "#991B1B"),
        "etf_row": ("#F9FAFB", "#111827"),
    }


class DataTable(ctk.CTkFrame):
    def __init__(self, master, columns: list[tuple[str, str, int]], **kwargs):
        super().__init__(master, corner_radius=6, **kwargs)
        self.columns = [key for key, _, _ in columns]
        self.tree = ttk.Treeview(self, columns=self.columns, show="headings", selectmode="browse")
        configure_treeview_theme(self.tree)

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

    def set_rows(self, rows: list[tuple[str, list[str]] | tuple[str, list[str], str]]) -> None:
        self.tree.delete(*self.tree.get_children())
        configure_treeview_tags(self.tree)
        for row in rows:
            if len(row) == 3:
                item_id, values, tag = row
                self.tree.insert("", "end", iid=str(item_id), values=values, tags=(tag,))
            else:
                item_id, values = row
                self.tree.insert("", "end", iid=str(item_id), values=values, tags=("etf_row",))

    def selected_id(self) -> int | None:
        selection = self.tree.selection()
        if not selection:
            return None
        try:
            return int(selection[0])
        except ValueError:
            return None


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
