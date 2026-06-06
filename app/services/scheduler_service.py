from __future__ import annotations

from collections.abc import Callable

from apscheduler.schedulers.background import BackgroundScheduler


class SchedulerService:
    def __init__(self):
        self.scheduler = BackgroundScheduler()

    def start_price_updates(self, callback: Callable[[], object], hours: int = 24) -> None:
        if not self.scheduler.running:
            self.scheduler.start()
        self.scheduler.add_job(callback, "interval", hours=hours, id="price_update", replace_existing=True)

    def stop(self) -> None:
        if self.scheduler.running:
            self.scheduler.shutdown(wait=False)
