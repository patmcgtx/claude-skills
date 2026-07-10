#!/usr/bin/env python3
"""Parse a YNAB "Budget" CSV export and summarize category health for one month.

Outputs JSON on stdout - the calling assistant should read this and narrate
the findings, not re-derive the numbers itself. Currency parsing and month
arithmetic are easy to get subtly wrong by eyeballing thousands of CSV rows,
so this script does that part deterministically.
"""
import argparse
import csv
import json
import sys
from collections import defaultdict
from datetime import datetime

EXPECTED_HEADERS = {
    "Month",
    "Category Group/Category",
    "Category Group",
    "Category",
    "Assigned",
    "Activity",
    "Available",
}


def parse_money(s):
    if s is None:
        return 0.0
    s = s.strip().replace(",", "").replace("$", "")
    if not s:
        return 0.0
    neg = s.startswith("-")
    if neg:
        s = s[1:]
    try:
        v = float(s)
    except ValueError:
        return 0.0
    return -v if neg else v


def load_rows(path):
    with open(path, encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        headers = set(reader.fieldnames or [])
        missing = EXPECTED_HEADERS - headers
        if missing:
            raise SystemExit(
                "This doesn't look like a YNAB 'Budget' export (missing columns: "
                f"{', '.join(sorted(missing))}). In YNAB, use the Budget page's "
                "'...' menu > Export Budget, and pick the plan/budget CSV "
                "(not the account register export - that one has Payee/Memo/"
                "Outflow/Inflow columns instead)."
            )
        rows = []
        for row in reader:
            rows.append(
                {
                    "month": row["Month"],
                    "category_group": row["Category Group"],
                    "category": row["Category"],
                    "full_name": row["Category Group/Category"],
                    "assigned": parse_money(row["Assigned"]),
                    "activity": parse_money(row["Activity"]),
                    "available": parse_money(row["Available"]),
                }
            )
        return rows


def month_key(m):
    return datetime.strptime(m, "%b %Y")


def fmt_row(r, **extra):
    out = {
        "category": r["full_name"],
        "assigned": round(r["assigned"], 2),
        "activity": round(r["activity"], 2),
        "available": round(r["available"], 2),
    }
    out.update(extra)
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("csv_path", help="Path to the YNAB Budget export CSV")
    ap.add_argument(
        "--month",
        help='Target month, e.g. "Jul 2026". Defaults to the most recent month present in the file.',
    )
    ap.add_argument(
        "--history",
        type=int,
        default=3,
        help="How many prior months to check for persistent overspending and spending trends (default 3)",
    )
    ap.add_argument(
        "--top",
        type=int,
        default=10,
        help="How many top-spending categories to report, with history for comparison (default 10)",
    )
    args = ap.parse_args()

    rows = load_rows(args.csv_path)
    all_months = sorted({r["month"] for r in rows}, key=month_key)
    if not all_months:
        raise SystemExit("No rows found in file.")

    target = args.month or all_months[-1]
    if target not in all_months:
        raise SystemExit(
            f"Month '{target}' not found in export. Months present include: "
            f"{', '.join(all_months[-6:])}"
        )

    target_idx = all_months.index(target)
    history_months = all_months[max(0, target_idx - args.history) : target_idx]

    by_month = defaultdict(list)
    for r in rows:
        by_month[r["month"]].append(r)

    target_rows = by_month[target]

    def is_hidden(r):
        return r["category_group"] == "Hidden Categories"

    def is_cc(r):
        return r["category_group"] == "Credit Card Payments"

    regular = [r for r in target_rows if not is_hidden(r) and not is_cc(r)]
    hidden = [r for r in target_rows if is_hidden(r)]
    cc = [r for r in target_rows if is_cc(r)]

    overspent = sorted(
        (r for r in regular if r["available"] < -0.005), key=lambda r: r["available"]
    )
    cc_overspent = sorted(
        (r for r in cc if r["available"] < -0.005), key=lambda r: r["available"]
    )
    hidden_active = [
        r for r in hidden if abs(r["assigned"]) > 0.005 or abs(r["activity"]) > 0.005
    ]
    spent_without_budget = [
        r for r in regular if abs(r["assigned"]) < 0.005 and r["activity"] < -0.005
    ]

    # Categories still technically funded but nearly drained - an early
    # warning before they tip into overspent. Exactly $0.00 available is
    # excluded on purpose: that's just a fixed bill (rent, HOA, child
    # support) paid in full, not a warning sign.
    running_low = sorted(
        (
            r
            for r in regular
            if r["assigned"] > 5 and 0 < r["available"] < 0.1 * r["assigned"]
        ),
        key=lambda r: r["available"] / r["assigned"],
    )

    persistent = []
    if history_months:
        prior_overspend_count = defaultdict(int)
        for m in history_months:
            for r in by_month[m]:
                if not is_hidden(r) and not is_cc(r) and r["available"] < -0.005:
                    prior_overspend_count[r["full_name"]] += 1
        for r in overspent:
            months = prior_overspend_count.get(r["full_name"], 0)
            if months > 0:
                persistent.append((r, months))

    group_totals = defaultdict(lambda: {"assigned": 0.0, "activity": 0.0, "available": 0.0})
    for r in regular:
        g = group_totals[r["category_group"]]
        g["assigned"] += r["assigned"]
        g["activity"] += r["activity"]
        g["available"] += r["available"]

    totals = {
        "assigned": sum(r["assigned"] for r in regular),
        "activity": sum(r["activity"] for r in regular),
        "available": sum(r["available"] for r in regular),
    }

    # Top spending categories this month, each with its activity in the prior
    # history months so spend can be compared to what's typical rather than
    # judged in isolation.
    history_activity_by_month = {
        m: {r["full_name"]: r["activity"] for r in by_month[m] if not is_hidden(r) and not is_cc(r)}
        for m in history_months
    }
    top_spending = sorted(
        (r for r in regular if r["activity"] < -0.005),
        key=lambda r: r["activity"],
    )[: args.top]

    top_spending_categories = []
    for r in top_spending:
        hist = {
            m: round(history_activity_by_month[m][r["full_name"]], 2)
            for m in history_months
            if r["full_name"] in history_activity_by_month[m]
        }
        avg = (sum(hist.values()) / len(hist)) if hist else None
        pct_change = None
        if avg is not None and abs(avg) > 0.005:
            # Positive means spent more than the historical average, negative
            # means less - computed off spend magnitude so the sign reads
            # naturally (activity itself is negative for outflow).
            pct_change = round((abs(r["activity"]) - abs(avg)) / abs(avg) * 100, 1)
        top_spending_categories.append(
            {
                "category": r["full_name"],
                "activity_current": round(r["activity"], 2),
                "activity_history": hist,
                "history_average": round(avg, 2) if avg is not None else None,
                "pct_change_vs_history_average": pct_change,
            }
        )

    result = {
        "target_month": target,
        "history_months_checked": history_months,
        "totals": {k: round(v, 2) for k, v in totals.items()},
        "group_totals": {
            g: {k: round(v, 2) for k, v in vals.items()}
            for g, vals in sorted(group_totals.items())
        },
        "top_spending_categories": top_spending_categories,
        "overspent_categories": [fmt_row(r) for r in overspent],
        "persistent_overspending": [
            fmt_row(r, prior_months_overspent=months) for r, months in persistent
        ],
        "running_low_categories": [fmt_row(r) for r in running_low],
        "spent_without_budget": [fmt_row(r) for r in spent_without_budget],
        "credit_card_overspent": [fmt_row(r) for r in cc_overspent],
        "hidden_categories_with_activity": [fmt_row(r) for r in hidden_active],
    }

    json.dump(result, sys.stdout, indent=2)
    print()


if __name__ == "__main__":
    main()
