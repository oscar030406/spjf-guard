"""Summarize the completed natural-calendar timed-work profile."""

import sys

sys.dont_write_bytecode = True

from natural_physical import RUN_DIR
from summarize_physical import summarize_run


def main() -> None:
    summarize_run(
        run_dir=RUN_DIR,
        profile="natural_original_calendar",
        title="Two-worker timed-work implementation — one selected original-calendar window",
        include_deadline=False,
    )


if __name__ == "__main__":
    main()
