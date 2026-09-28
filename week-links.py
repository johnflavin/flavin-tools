#!/usr/bin/env python3

"""
Print a bulleted list of Obsidian links to weekly notes, e.g.

    - [[Week of 2026-09-28]]
    - [[Week of 2026-10-05]]
    ...

Starts at the Monday of the current week (or of --start) and emits --count weeks.

Intended use:
    week-links.py | pbcopy
"""

import argparse
import datetime
import sys


def monday_of(day: datetime.date) -> datetime.date:
    return day - datetime.timedelta(days=day.weekday())


def week_links(start: datetime.date, count: int) -> list[str]:
    first = monday_of(start)
    return [
        f"- [[Week of {first + datetime.timedelta(weeks=i):%Y-%m-%d}]]"
        for i in range(count)
    ]


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument(
        "-s", "--start",
        type=datetime.date.fromisoformat,
        default=datetime.date.today(),
        help="Any date in the first week, YYYY-MM-DD (default: today)",
    )
    parser.add_argument(
        "-n", "--count",
        type=int,
        default=12,
        help="Number of weeks to list (default: 12)",
    )
    args = parser.parse_args(argv)

    print("\n".join(week_links(args.start, args.count)))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
