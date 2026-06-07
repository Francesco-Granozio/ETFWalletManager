from __future__ import annotations

from datetime import date, datetime
from importlib import import_module
from typing import Protocol

from app.domain import PortfolioPosition, PriceQuote, PriceUpdateResult


class PriceProvider(Protocol):
    def fetch(self, isin: str) -> PriceQuote: ...


DEFAULT_PRICE_PROVIDER = "ls"


def create_price_provider(provider: str | None = None) -> PriceProvider:
    selected = (provider or DEFAULT_PRICE_PROVIDER).strip().lower()
    if selected in {"ls", "lsx", "l&s", "lang-schwarz", "lang_schwarz"}:
        return LangSchwarzPriceProvider()
    if selected in {"justetf", "justetf-gettex", "gettex"}:
        return JustEtfPriceProvider()
    raise ValueError(f"Unknown price provider: {provider}")


class JustEtfPriceProvider:
    source = "justETF Gettex"

    def fetch(self, isin: str) -> PriceQuote:
        module = import_module("justetf_scraping")
        quote = module.load_live_quote(isin)
        price = _quote_price(quote)
        if price is None or price <= 0:
            raise ValueError(f"No valid live price for {isin}")
        return PriceQuote(
            isin=isin,
            price=price,
            price_date=_quote_date(quote),
            source=self.source,
            currency=_quote_field(quote, "currency") or "EUR",
            exchange=(_quote_field(quote, "exchange") or "GETTEX").upper(),
        )


class LangSchwarzPriceProvider:
    source = "Lang & Schwarz LSX"

    def __init__(self, scraper: object | None = None):
        self.scraper = scraper

    def fetch(self, isin: str) -> PriceQuote:
        normalized_isin = isin.strip().upper()
        quote = self._scraper().get_quote(normalized_isin)
        price = _quote_price(quote)
        if price is None or price <= 0:
            raise ValueError(f"No valid Lang & Schwarz price for {normalized_isin}")
        return PriceQuote(
            isin=normalized_isin,
            price=price,
            price_date=_quote_date(quote),
            source=self.source,
            currency=_quote_field(quote, "currency") or "EUR",
            exchange=_quote_field(quote, "exchange") or "LSX",
        )

    def _scraper(self) -> object:
        if self.scraper is None:
            from app.services.lang_schwarz_scraper import LangSchwarzScraper

            self.scraper = LangSchwarzScraper()
        return self.scraper


class PriceService:
    def __init__(self, provider: PriceProvider | None = None):
        self.provider = provider or create_price_provider()

    def update_current_prices(self, repository) -> list[PriceUpdateResult]:
        results: list[PriceUpdateResult] = []
        for position in repository.list_positions():
            try:
                quote = self.provider.fetch(position.isin)
            except Exception as exc:
                results.append(_failure(position, exc))
                continue

            repository.save_price(
                position.etf_id,
                price=quote.price,
                price_date=quote.price_date,
                source=quote.source,
            )
            results.append(
                PriceUpdateResult(
                    isin=position.isin,
                    ok=True,
                    price=quote.price,
                    source=quote.source,
                    message="updated",
                )
            )
        return results


def _failure(position: PortfolioPosition, exc: Exception) -> PriceUpdateResult:
    return PriceUpdateResult(
        isin=position.isin,
        ok=False,
        price=position.price,
        source=position.price_source,
        message=str(exc) or exc.__class__.__name__,
    )


def _quote_price(quote: object) -> float | None:
    for field in ("price", "bid", "mid", "ask", "last"):
        value = _quote_field(quote, field)
        if value is not None:
            return float(value)
    return None


def _quote_date(quote: object) -> date:
    timestamp = _quote_field(quote, "timestamp")
    if isinstance(timestamp, datetime):
        return timestamp.date()
    if isinstance(timestamp, date):
        return timestamp
    return date.today()


def _quote_field(quote: object, field: str):
    if isinstance(quote, dict):
        return quote.get(field)
    return getattr(quote, field, None)
