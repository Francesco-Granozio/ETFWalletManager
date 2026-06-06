from datetime import date

from app.db.database import create_session_factory, init_database
from app.db.repositories import PortfolioRepository
from app.domain import EtfMetadata
from app.services.etf_metadata_service import EtfMetadataService


def metadata(isin: str = "IE000XZSV718") -> EtfMetadata:
    return EtfMetadata(
        isin=isin,
        name="SPDR S&P 500 UCITS ETF (Acc)",
        segment="S&P 500",
        ticker="SPYL",
        exchange="GETTEX",
        currency="EUR",
        ter=0.0003,
        price=14.56,
        price_date=date(2026, 6, 6),
        price_source="justETF",
    )


class CountingProvider:
    def __init__(self):
        self.calls: list[str] = []

    def fetch(self, isin: str) -> EtfMetadata:
        self.calls.append(isin)
        return metadata(isin)


def test_metadata_service_uses_repository_cache_before_scraping(tmp_path):
    session_factory = create_session_factory(tmp_path / "portfolio.db")
    init_database(session_factory)
    provider = CountingProvider()
    service = EtfMetadataService(provider)

    with session_factory() as session:
        repo = PortfolioRepository(session)

        first = service.resolve(repo, "ie000xzsv718")
        second = service.resolve(repo, "IE000XZSV718")
        refreshed = service.resolve(repo, "IE000XZSV718", force_refresh=True)

        assert first == metadata()
        assert second == metadata()
        assert refreshed == metadata()
        assert provider.calls == ["IE000XZSV718", "IE000XZSV718"]
