from __future__ import annotations

import argparse

from app.app_context import AppContext
from app.db.database import create_session_factory, init_database
from app.ui.main_window import MainWindow


def build_context(db_path=None) -> AppContext:
    session_factory = create_session_factory() if db_path is None else create_session_factory(db_path)
    init_database(session_factory)
    return AppContext(session_factory)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--smoke", action="store_true", help="Initialize database and print a compact status.")
    parser.add_argument("--db-path", default=None, help="Override SQLite database path.")
    args = parser.parse_args(argv)

    context = build_context(args.db_path)
    if args.smoke:
        allocation = context.allocation_summary()
        print(f"positions={len(allocation.rows)} total={allocation.total_value:.2f}")
        return 0

    window = MainWindow(context)
    window.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
