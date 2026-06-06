from __future__ import annotations

from calendar import monthrange
from datetime import date
from importlib import import_module
from typing import Protocol

from app.domain import (
    HistoricalPriceQuote,
    PAC_EXECUTION_SCHEDULE_OPTIONS,
    PacExecution,
)

MONTH_NAMES = (
    "",
    "Gennaio",
    "Febbraio",
    "Marzo",
    "Aprile",
    "Maggio",
    "Giugno",
    "Luglio",
    "Agosto",
    "Settembre",
    "Ottobre",
    "Novembre",
    "Dicembre",
)


class HistoricalPriceProvider(Protocol):
    def fetch(self, isin: str, target_date: date, currency: str = "EUR") -> HistoricalPriceQuote: ...


class JustEtfHistoricalPriceProvider:
    source = "justETF chart"

    def fetch(self, isin: str, target_date: date, currency: str = "EUR") -> HistoricalPriceQuote:
        module = import_module("justetf_scraping")
        chart = module.load_chart(isin, currency=currency)
        if chart.empty:
            raise ValueError(f"Nessun dato storico justETF per {isin}")

        target = _timestamp(target_date)
        if target in chart.index:
            price_date = target.date()
            price = float(chart.at[target, "quote"])
        else:
            previous = chart[chart.index <= target]
            selected = previous.tail(1) if not previous.empty else chart[chart.index > target].head(1)
            if selected.empty:
                raise ValueError(f"Nessun prezzo justETF vicino a {target_date:%d/%m/%Y} per {isin}")
            price_date = selected.index[0].date()
            price = float(selected.iloc[0]["quote"])

        if price <= 0:
            raise ValueError(f"Prezzo storico non valido per {isin}")
        return HistoricalPriceQuote(
            isin=isin,
            price=price,
            price_date=price_date,
            source=self.source,
            currency=currency,
        )


class PacExecutionService:
    def __init__(self, price_provider: HistoricalPriceProvider | None = None):
        self.price_provider = price_provider or JustEtfHistoricalPriceProvider()

    def ensure_due_executions(self, repository, today: date) -> list[PacExecution]:
        simulation = repository.get_active_simulation()
        if simulation is None:
            return []

        active_from = (simulation.applied_at or simulation.created_at).date()
        latest_date = repository.latest_pac_execution_date(simulation.id)
        due_dates = schedule_due_dates(
            simulation.execution_schedule,
            active_from=active_from,
            today=today,
            after=latest_date,
        )

        created: list[PacExecution] = []
        for execution_date in due_dates:
            created.append(
                repository.save_pac_execution_from_simulation(
                    simulation,
                    execution_date=execution_date,
                    name=default_execution_name(simulation.execution_schedule, execution_date),
                    manual=False,
                    quotes=self._quotes_for(simulation.rows, execution_date),
                )
            )
        return created

    def create_manual_execution(
        self,
        repository,
        simulation_id: int,
        execution_date: date,
        name: str | None = None,
    ) -> PacExecution:
        simulation = repository.get_simulation(simulation_id)
        if simulation is None:
            raise ValueError(f"PAC non trovato: {simulation_id}")
        return repository.save_pac_execution_from_simulation(
            simulation,
            execution_date=execution_date,
            name=name or default_execution_name(simulation.execution_schedule, execution_date),
            manual=True,
            quotes=self._quotes_for(simulation.rows, execution_date),
        )

    def _quotes_for(self, rows, execution_date: date) -> dict[str, HistoricalPriceQuote]:
        quotes: dict[str, HistoricalPriceQuote] = {}
        for row in rows:
            try:
                quotes[row.metadata.isin] = self.price_provider.fetch(
                    row.metadata.isin,
                    execution_date,
                    row.metadata.currency,
                )
            except Exception:
                continue
        return quotes


def schedule_due_dates(
    schedule: str,
    active_from: date,
    today: date,
    after: date | None = None,
) -> list[date]:
    if today < active_from:
        return []
    selected = _validate_schedule(schedule)
    candidates = _candidate_dates(selected, active_from, today)
    return [
        item
        for item in candidates
        if item >= active_from and item <= today and (after is None or item > after)
    ]


def default_execution_name(schedule: str, execution_date: date) -> str:
    selected = _validate_schedule(schedule)
    day_month = f"{execution_date.day} {MONTH_NAMES[execution_date.month]}"
    if selected.startswith("Settimanale"):
        start_day = _start_day(selected)
        week_number = ((execution_date.day - start_day) // 7) + 1
        return f"Esecuzione Settimana {week_number} inizio {day_month}"
    if selected.startswith("2 volte"):
        part = _twice_monthly_part(selected, execution_date)
        return f"Esecuzione Mensile {part} inizio {day_month}"
    if selected.startswith("Ogni 3 mesi"):
        return f"Esecuzione trimestrale inizio {day_month}"
    return f"Esecuzione mensile inizio {day_month}"


def _candidate_dates(schedule: str, active_from: date, today: date) -> list[date]:
    if schedule.startswith("Settimanale"):
        return _weekly_dates(_start_day(schedule), active_from, today)
    if schedule.startswith("2 volte"):
        return _twice_monthly_dates(_start_day(schedule), active_from, today)
    if schedule.startswith("Ogni 3 mesi"):
        return _quarterly_dates(_start_day(schedule), active_from, today)
    return _monthly_dates(_start_day(schedule), active_from, today)


def _weekly_dates(start_day: int, active_from: date, today: date) -> list[date]:
    dates: list[date] = []
    year, month = active_from.year, active_from.month
    while (year, month) <= (today.year, today.month):
        days_in_month = monthrange(year, month)[1]
        day = start_day
        while day <= days_in_month:
            dates.append(date(year, month, day))
            day += 7
        year, month = _next_month(year, month)
    return sorted(dates)


def _twice_monthly_dates(start_day: int, active_from: date, today: date) -> list[date]:
    dates: list[date] = []
    first_anchor = date(active_from.year, active_from.month, min(start_day, monthrange(active_from.year, active_from.month)[1]))
    year, month = active_from.year, active_from.month
    while (year, month) <= (today.year, today.month):
        for day in (2, 16):
            if day <= monthrange(year, month)[1]:
                candidate = date(year, month, day)
                if candidate >= first_anchor:
                    dates.append(candidate)
        year, month = _next_month(year, month)
    return sorted(dates)


def _monthly_dates(start_day: int, active_from: date, today: date) -> list[date]:
    dates: list[date] = []
    year, month = active_from.year, active_from.month
    while (year, month) <= (today.year, today.month):
        day = min(start_day, monthrange(year, month)[1])
        dates.append(date(year, month, day))
        year, month = _next_month(year, month)
    return sorted(dates)


def _quarterly_dates(start_day: int, active_from: date, today: date) -> list[date]:
    dates: list[date] = []
    year, month = active_from.year, active_from.month
    day = min(start_day, monthrange(year, month)[1])
    current = date(year, month, day)
    if current < active_from:
        year, month = _add_months(year, month, 3)
        current = date(year, month, min(start_day, monthrange(year, month)[1]))
    while current <= today:
        dates.append(current)
        year, month = _add_months(current.year, current.month, 3)
        current = date(year, month, min(start_day, monthrange(year, month)[1]))
    return dates


def _twice_monthly_part(schedule: str, execution_date: date) -> int:
    start_day = _start_day(schedule)
    if start_day == 16:
        return 1 if execution_date.day == 16 else 2
    return 1 if execution_date.day == 2 else 2


def _start_day(schedule: str) -> int:
    return 16 if "16" in schedule else 2


def _validate_schedule(schedule: str) -> str:
    selected = schedule.strip()
    if selected not in PAC_EXECUTION_SCHEDULE_OPTIONS:
        raise ValueError(f"Frequenza PAC non valida: {schedule}")
    return selected


def _next_month(year: int, month: int) -> tuple[int, int]:
    return _add_months(year, month, 1)


def _add_months(year: int, month: int, amount: int) -> tuple[int, int]:
    index = (year * 12) + month - 1 + amount
    return index // 12, (index % 12) + 1


def _timestamp(value: date):
    import pandas as pd

    return pd.Timestamp(value)
