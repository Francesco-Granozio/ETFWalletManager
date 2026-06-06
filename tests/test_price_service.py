from datetime import date

from app.domain import PortfolioPosition, PriceQuote
from app.services.price_service import PriceService, _quote_price


def position(isin: str) -> PortfolioPosition:
    return PortfolioPosition(
        etf_id=42,
        asset_class="Azioni",
        segment="Segment",
        name=isin,
        isin=isin,
        ticker=None,
        exchange="GETTEX",
        currency="EUR",
        ter=0.001,
        target_pct=1.0,
        target_segment_pct=None,
        quantity=1,
        average_price=10,
        price=10,
        price_date=date(2026, 6, 6),
        price_source="manual",
        enabled=True,
    )


class FakeProvider:
    def __init__(self, quote=None, error=None):
        self.quote = quote
        self.error = error

    def fetch(self, isin: str):
        if self.error:
            raise self.error
        return self.quote


class FakeRepository:
    def __init__(self):
        self.positions = [position("IE000TEST001")]
        self.saved = []

    def list_positions(self):
        return self.positions

    def save_price(self, etf_id, price, price_date, source):
        self.saved.append((etf_id, price, price_date, source))


def test_price_service_saves_provider_quote_to_repository():
    repo = FakeRepository()
    provider = FakeProvider(
        PriceQuote(
            isin="IE000TEST001",
            price=12.3,
            price_date=date(2026, 6, 8),
            source="justETF Gettex",
        )
    )

    results = PriceService(provider).update_current_prices(repo)

    assert results[0].ok is True
    assert repo.saved == [(42, 12.3, date(2026, 6, 8), "justETF Gettex")]


def test_price_service_reports_error_without_overwriting_cached_price():
    repo = FakeRepository()
    provider = FakeProvider(error=TimeoutError("timeout"))

    results = PriceService(provider).update_current_prices(repo)

    assert results[0].ok is False
    assert results[0].price == 10
    assert "timeout" in results[0].message
    assert repo.saved == []


def test_quote_price_prefers_bid_over_stale_last_price():
    quote = {
        "last": 16.12,
        "mid": 15.77,
        "ask": 15.82,
        "bid": 15.71,
    }

    assert _quote_price(quote) == 15.71
