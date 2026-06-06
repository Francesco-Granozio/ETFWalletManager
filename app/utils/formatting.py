from __future__ import annotations

from datetime import date


def money(value: float | None) -> str:
    if value is None:
        return "-"
    return f"{value:,.2f} EUR".replace(",", "X").replace(".", ",").replace("X", ".")


def pct(value: float | None) -> str:
    if value is None:
        return "-"
    return f"{value * 100:.2f}%".replace(".", ",")


def number(value: float | None, digits: int = 4) -> str:
    if value is None:
        return "-"
    return f"{value:.{digits}f}".replace(".", ",")


def date_text(value: date | None) -> str:
    if value is None:
        return "-"
    return value.strftime("%d/%m/%Y")


def parse_decimal(text: str) -> float:
    cleaned = text.strip().replace(" ", "")
    if "," in cleaned and "." in cleaned:
        decimal_separator = "," if cleaned.rfind(",") > cleaned.rfind(".") else "."
        thousands_separator = "." if decimal_separator == "," else ","
        cleaned = cleaned.replace(thousands_separator, "").replace(decimal_separator, ".")
    elif "," in cleaned:
        cleaned = cleaned.replace(".", "").replace(",", ".")
    elif cleaned.count(".") > 1:
        parts = cleaned.split(".")
        cleaned = "".join(parts[:-1]) + "." + parts[-1]
    return float(cleaned)
