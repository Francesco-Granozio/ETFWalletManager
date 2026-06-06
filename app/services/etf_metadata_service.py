from __future__ import annotations

from datetime import date, datetime
from importlib import import_module
from math import isnan
from typing import Protocol

from app.domain import EtfMetadata


class EtfMetadataProvider(Protocol):
    def fetch(self, isin: str) -> EtfMetadata: ...


class JustEtfMetadataProvider:
    source = "justETF"

    def fetch(self, isin: str) -> EtfMetadata:
        normalized = normalize_isin(isin)
        module = import_module("justetf_scraping")
        profile: object | None = None
        overview_row: dict[str, object] = {}
        profile_error: Exception | None = None
        overview_error: Exception | None = None

        try:
            profile = module.get_etf_overview(
                normalized,
                include_gettex=True,
                expand_allocations=False,
            )
        except Exception as exc:
            profile_error = exc

        try:
            overview_row = _load_overview_row(module, normalized)
        except Exception as exc:
            overview_error = exc

        if profile is None and not overview_row:
            message = str(profile_error or overview_error or "ETF metadata not found")
            raise ValueError(f"Impossibile risolvere {normalized} da justETF: {message}")

        quote = _field(profile, "gettex")
        name = _first_text(
            _field(profile, "name"),
            overview_row.get("name"),
            normalized,
        )
        segment = _first_text(
            _field(profile, "index"),
            _field(profile, "investment_focus"),
            overview_row.get("name"),
            name,
        )
        ticker = _optional_text(overview_row.get("ticker"))
        currency = _first_text(
            _quote_field(quote, "currency"),
            _field(profile, "fund_currency"),
            overview_row.get("currency"),
            "EUR",
        )
        price = _quote_price(quote) or 0.0
        price_date = _quote_date(quote)
        ter = _ter_ratio(_first_number(_field(profile, "ter"), overview_row.get("ter")))

        return EtfMetadata(
            isin=normalized,
            name=name,
            segment=segment,
            ticker=ticker,
            exchange=_first_text(_quote_field(quote, "exchange"), "GETTEX"),
            currency=currency,
            ter=ter,
            price=price,
            price_date=price_date,
            price_source=self.source if price > 0 else "justETF metadata",
        )


class EtfMetadataService:
    def __init__(self, provider: EtfMetadataProvider | None = None):
        self.provider = provider or JustEtfMetadataProvider()

    def resolve(self, repository, isin: str, force_refresh: bool = False) -> EtfMetadata:
        normalized = normalize_isin(isin)
        if not force_refresh:
            cached = repository.get_etf_metadata(normalized)
            if cached is not None:
                return cached
        metadata = self.provider.fetch(normalized)
        return repository.save_etf_metadata(metadata)


def normalize_isin(isin: str) -> str:
    return isin.strip().upper()


def _load_overview_row(module: object, isin: str) -> dict[str, object]:
    frame = module.load_overview(isin=isin, language="en", local_country="IT", currency="EUR")
    if getattr(frame, "empty", True):
        return {}
    if isin in frame.index:
        row = frame.loc[isin]
    else:
        row = frame.iloc[0]
    return {key: row[key] for key in row.index}


def _field(source: object | None, key: str) -> object | None:
    if source is None:
        return None
    if isinstance(source, dict):
        return source.get(key)
    return getattr(source, key, None)


def _quote_field(quote: object | None, key: str) -> object | None:
    return _field(quote, key)


def _quote_price(quote: object | None) -> float | None:
    for key in ("last", "mid", "ask", "bid"):
        value = _first_number(_quote_field(quote, key))
        if value is not None and value > 0:
            return value
    return None


def _quote_date(quote: object | None) -> date | None:
    timestamp = _quote_field(quote, "timestamp")
    if isinstance(timestamp, datetime):
        return timestamp.date()
    if isinstance(timestamp, date):
        return timestamp
    return None


def _ter_ratio(value: float | None) -> float:
    if value is None:
        return 0.0
    return value / 100


def _first_text(*values: object) -> str:
    for value in values:
        text = _optional_text(value)
        if text:
            return text
    return ""


def _optional_text(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text or text.lower() == "nan":
        return None
    return text


def _first_number(*values: object) -> float | None:
    for value in values:
        if value is None:
            continue
        try:
            number = float(value)
        except (TypeError, ValueError):
            continue
        if isnan(number):
            continue
        return number
    return None
