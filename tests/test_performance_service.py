from datetime import date

from app.domain import PortfolioSnapshot
from app.services.performance_service import PerformanceService, period_starts


class FakeSnapshotRepository:
    def __init__(self):
        self.snapshots = {}

    def get_snapshot(self, snapshot_date: date):
        return self.snapshots.get(snapshot_date)

    def save_snapshot(self, snapshot: PortfolioSnapshot):
        self.snapshots[snapshot.date] = snapshot
        return snapshot

    def list_snapshots(self):
        return sorted(self.snapshots.values(), key=lambda item: item.date)


def test_period_starts_use_first_day_boundaries():
    periods = period_starts(date(2026, 6, 10))

    assert periods.current == date(2026, 6, 1)
    assert periods.previous_month == date(2026, 5, 1)
    assert periods.year_start == date(2026, 1, 1)
    assert periods.previous_year == date(2025, 6, 1)


def test_performance_report_uses_fixed_existing_snapshots():
    repo = FakeSnapshotRepository()
    repo.save_snapshot(PortfolioSnapshot(date(2026, 6, 1), 6200, 4000, 1500, 700))
    repo.save_snapshot(PortfolioSnapshot(date(2026, 5, 1), 6000, 3900, 1450, 650))
    repo.save_snapshot(PortfolioSnapshot(date(2026, 1, 1), 5400, 3500, 1400, 500))
    repo.save_snapshot(PortfolioSnapshot(date(2025, 6, 1), 4800, 3200, 1200, 400))
    service = PerformanceService(repo)

    report = service.build_report(date(2026, 6, 10))

    assert report.current.date == date(2026, 6, 1)
    assert report.monthly_diff == 200
    assert round(report.monthly_diff_pct, 4) == 0.0333
    assert report.ytd_diff == 800
    assert round(report.ytd_diff_pct, 4) == 0.1481
    assert report.yearly_diff == 1400
    assert round(report.yearly_diff_pct, 4) == 0.2917
