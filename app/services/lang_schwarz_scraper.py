from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal, InvalidOperation
import json
import re
import time
from typing import Any
from zoneinfo import ZoneInfo

import requests
from bs4 import BeautifulSoup


LS_BASE = "https://www.ls-tc.de"
LS_TZ = ZoneInfo("Europe/Berlin")


@dataclass(frozen=True)
class LangSchwarzQuote:
    isin: str
    exchange: str
    price: Decimal
    bid: Decimal | None
    ask: Decimal | None
    mid: Decimal | None
    last: Decimal | None
    timestamp: datetime | None
    currency: str | None
    name: str | None
    raw_payload: dict[str, Any]


class LangSchwarzScraper:
    def __init__(
        self,
        *,
        locale_id: int = 2,
        exchange: str = "LSX",
        timeout: float = 10.0,
        min_delay_sec: float = 0.5,
    ) -> None:
        self.locale_id = locale_id
        self.exchange = exchange
        self.timeout = timeout
        self.min_delay_sec = min_delay_sec
        self.session = requests.Session()
        self.session.headers.update(
            {
                "User-Agent": (
                    "Mozilla/5.0 (compatible; portfolio-price-checker/1.0; "
                    "+https://example.local)"
                ),
                "Accept": "text/html,application/json;q=0.9,*/*;q=0.8",
                "Accept-Language": "en,de;q=0.8,it;q=0.7",
            }
        )

    def get_quote(self, isin: str) -> LangSchwarzQuote:
        normalized_isin = isin.strip().upper()
        instrument = self._find_instrument(normalized_isin)
        instrument_id = instrument["id"]
        page_url, html = self._fetch_instrument_page(instrument_id, instrument)
        parsed = self._parse_quote_page(
            html,
            isin=normalized_isin,
            page_url=page_url,
        )

        bid = parsed["bid"]
        ask = parsed["ask"]
        last = parsed["last"]
        mid = (bid + ask) / Decimal("2") if bid is not None and ask is not None else None

        if bid is None:
            raise ValueError(f"No bid found for ISIN {normalized_isin}")

        return LangSchwarzQuote(
            isin=normalized_isin,
            exchange=self.exchange,
            price=bid,
            bid=bid,
            ask=ask,
            mid=mid,
            last=last,
            timestamp=parsed["timestamp"],
            currency=parsed["currency"],
            name=parsed["name"],
            raw_payload={
                "source": "ls-tc.de",
                "instrument_search": instrument,
                "page_url": page_url,
                "parsed": {
                    "bid": str(bid) if bid is not None else None,
                    "ask": str(ask) if ask is not None else None,
                    "mid": str(mid) if mid is not None else None,
                    "last": str(last) if last is not None else None,
                    "timestamp": (
                        parsed["timestamp"].isoformat()
                        if parsed["timestamp"] is not None
                        else None
                    ),
                    "currency": parsed["currency"],
                    "name": parsed["name"],
                },
                "html_excerpt": html[:5000],
            },
        )

    def _find_instrument(self, isin: str) -> dict[str, Any]:
        url = f"{LS_BASE}/_rpc/json/.lstc/instrument/search/main"
        response = self.session.get(
            url,
            params={"q": isin, "localeId": self.locale_id},
            timeout=self.timeout,
        )
        response.raise_for_status()

        try:
            data = response.json()
        except json.JSONDecodeError as exc:
            raise ValueError(f"Instrument search response is not JSON for {isin}") from exc

        if not isinstance(data, list) or not data:
            raise LookupError(f"No Lang & Schwarz instrument found for ISIN {isin}")

        exact = [item for item in data if str(item.get("isin", "")).upper() == isin]
        chosen = exact[0] if exact else data[0]
        if "id" not in chosen:
            raise ValueError(f"Instrument search response has no id: {chosen}")
        return chosen

    def _fetch_instrument_page(
        self,
        instrument_id: int | str,
        instrument: dict[str, Any],
    ) -> tuple[str, str]:
        candidates: list[str] = []
        for key in ("url", "link", "path"):
            value = instrument.get(key)
            if isinstance(value, str) and value:
                candidates.append(value if value.startswith("http") else f"{LS_BASE}{value}")

        for kind in ("stock", "etf", "fund", "bond", "certificate"):
            candidates.append(f"{LS_BASE}/en/{kind}/{instrument_id}")

        last_error: Exception | None = None
        for url in _unique(candidates):
            time.sleep(self.min_delay_sec)
            try:
                response = self.session.get(url, timeout=self.timeout)
                if response.status_code == 404:
                    continue
                response.raise_for_status()
                html = response.text
                if "Bid" in html or "Geld" in html:
                    return response.url, html
            except requests.RequestException as exc:
                last_error = exc

        raise LookupError(f"Lang & Schwarz detail page not found for {instrument_id}") from last_error

    def _parse_quote_page(
        self,
        html: str,
        *,
        isin: str,
        page_url: str,
    ) -> dict[str, Any]:
        soup = BeautifulSoup(html, "html.parser")
        text = soup.get_text("\n", strip=True)

        name = self._extract_name(text)
        page_isin = self._extract_after_label(text, "ISIN")
        if page_isin and page_isin.upper() != isin:
            raise ValueError(f"ISIN mismatch: requested {isin}, page contains {page_isin}")

        bid = self._extract_price_after_any_label(text, ["Bid", "Geld"])
        ask = self._extract_price_after_any_label(text, ["Ask", "Brief"])
        last, timestamp = self._extract_main_quote(text, isin=isin)
        currency = "EUR"

        return {
            "name": name,
            "bid": bid,
            "ask": ask,
            "last": last,
            "timestamp": timestamp,
            "currency": currency,
            "page_url": page_url,
        }

    def _extract_name(self, text: str) -> str | None:
        lines = _text_lines(text)
        for index, line in enumerate(lines):
            if line.startswith("ISIN:") and index > 0:
                return lines[index - 1]
        for index, line in enumerate(lines):
            if line in {"Name", "Name:", "Stammdaten"} and index + 1 < len(lines):
                return lines[index + 1]
        return None

    def _extract_after_label(self, text: str, label: str) -> str | None:
        pattern = rf"{re.escape(label)}:\s*([A-Z0-9]{{12}})"
        match = re.search(pattern, text)
        return match.group(1) if match else None

    def _extract_price_after_any_label(self, text: str, labels: list[str]) -> Decimal | None:
        lines = _text_lines(text)
        for index, line in enumerate(lines):
            if line in labels:
                for candidate in lines[index + 1 : index + 5]:
                    value = self._parse_decimal_from_text(candidate)
                    if value is not None:
                        return value
        return None

    def _extract_main_quote(
        self,
        text: str,
        *,
        isin: str,
    ) -> tuple[Decimal | None, datetime | None]:
        lines = _text_lines(text)
        isin_index = next(
            (index for index, line in enumerate(lines) if "ISIN:" in line and isin in line),
            None,
        )
        if isin_index is None:
            return None, None

        price: Decimal | None = None
        timestamp: datetime | None = None
        for line in lines[isin_index + 1 : isin_index + 12]:
            if price is None and not _looks_like_ls_date_time(line):
                price = self._parse_decimal_from_text(line)
            if timestamp is None:
                timestamp = self._parse_timestamp_line(line)
            if price is not None and timestamp is not None:
                return price, timestamp
        return price, timestamp

    def _parse_timestamp_line(self, line: str) -> datetime | None:
        match = re.search(
            r"(?P<date>\d{2}\.\d{2}\.)\s+(?P<time>\d{2}:\d{2}(?::\d{2})?)",
            line,
        )
        if not match:
            return None
        return self._parse_ls_timestamp(
            date_part=match.group("date"),
            time_part=match.group("time"),
        )

    def _parse_ls_timestamp(
        self,
        *,
        date_part: str | None,
        time_part: str,
    ) -> datetime | None:
        now = datetime.now(LS_TZ)
        try:
            if date_part:
                day, month, _ = date_part.split(".")
                date_text = f"{now.year}-{int(month):02d}-{int(day):02d}"
            else:
                date_text = now.strftime("%Y-%m-%d")

            if len(time_part.split(":")) == 2:
                time_part = f"{time_part}:00"
            return datetime.fromisoformat(f"{date_text}T{time_part}").replace(tzinfo=LS_TZ)
        except ValueError:
            return None

    def _normalize_currency(self, value: str | None) -> str | None:
        if value is None:
            return None
        return {"\u20ac": "EUR", "$": "USD"}.get(value.strip().upper(), value.strip().upper())

    def _parse_decimal_from_text(self, value: str | None) -> Decimal | None:
        if not value:
            return None

        cleaned = (
            value.replace("\xa0", " ")
            .replace("\u20ac", "")
            .replace("$", "")
            .replace("EUR", "")
            .replace("USD", "")
            .replace("CHF", "")
            .replace("GBP", "")
            .strip()
        )
        match = re.search(r"[+-]?\d[\d.,]*", cleaned)
        if not match:
            return None

        number = match.group(0)
        if "," in number and "." in number:
            if number.rfind(",") > number.rfind("."):
                number = number.replace(".", "").replace(",", ".")
            else:
                number = number.replace(",", "")
        elif "," in number:
            number = number.replace(",", ".")

        try:
            return Decimal(number)
        except InvalidOperation:
            return None


def _text_lines(text: str) -> list[str]:
    return [line.strip() for line in text.splitlines() if line.strip()]


def _looks_like_ls_date_time(text: str) -> bool:
    return re.fullmatch(r"\d{2}\.\d{2}\.\s+\d{2}:\d{2}(?::\d{2})?", text.strip()) is not None


def _unique(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        if value in seen:
            continue
        result.append(value)
        seen.add(value)
    return result
