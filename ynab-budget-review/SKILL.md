---
name: ynab-budget-review
description: Reviews a YNAB (You Need A Budget) "Budget" CSV export to check category health - overspending, categories running low, spending that happened without a budgeted amount, and stray activity in hidden or credit-card-payment categories. Use this whenever the user shares a YNAB export file, mentions YNAB, or asks things like "review my budget," "how's my budget looking," "am I overspending," "check my categories," or "how did I do this month" in a budgeting context - even if they don't say "YNAB" explicitly, e.g. someone asking to review a CSV with columns like Category Group, Assigned, Activity, Available.
---

# YNAB Budget Review

Reviews a YNAB "Budget" export (category-level, not the transaction register export) and gives a conversational summary of budget health for a chosen month: what's overspent, what's about to be, and anything unusual.

## Why a script instead of reading the CSV directly

These exports are often the *entire* budget history - one row per category per month, going back years, frequently 5,000+ rows. Eyeballing that or manually summing activity across rows is slow and error-prone (currency strings, sign conventions, and YNAB's special category groups are easy to get subtly wrong at that volume). `scripts/analyze_budget.py` parses the file once and returns the exact numbers as JSON; treat those numbers as ground truth and spend your effort on the narrative, not on re-deriving arithmetic.

## Running the review

1. **Find the file.** If the user didn't give a path, ask for one, or check their Downloads folder for something named like `YNAB Export ... - Plan.csv` (that's the default export filename).
2. **Run the script:**
   ```
   python3 scripts/analyze_budget.py "<path-to-export.csv>"
   ```
   By default it targets the most recent month present in the file, checks the prior 3 months for persistent overspending and spending trends, and reports the top 10 spend categories. Override with `--month "Jul 2026"`, `--history 6`, or `--top 5` if the user asks about a specific month, wants a longer lookback, or only cares about a handful of categories.
3. **If the script errors** because the columns don't match, that almost always means the user exported the account register (transactions) instead of the budget/plan view. Relay the script's error message - it already explains the fix (Budget page > "..." menu > Export Budget).
4. **Read the JSON** and narrate it - don't just dump it back at the user. See below for what each field means and how to weigh it.

## What the fields mean and how to talk about them

- **`overspent_categories`** - categories with negative `available` this month. This is the headline: lead with these if there are any, ordered worst-first (the script already sorts them that way).
- **`persistent_overspending`** - a subset of the above that were *also* overspent in prior months (`prior_months_overspent` counts how many). Call these out distinctly - a category overspent for the first time is a one-off to explain, but one that's overspent three months running usually means the assigned amount itself is wrong and should be raised, not that spending needs to be reined in. Frame the recommendation accordingly.
- **`running_low_categories`** - still positive but under 10% of what was assigned, excluding the common case of a fixed bill spent down to exactly $0.00 (that's normal for things like rent or a car payment, not a warning). These are worth a soft heads-up ("X is close to tapped out") rather than alarm.
- **`spent_without_budget`** - activity happened in a category with nothing assigned to it this month. Depending on the category this might be a one-off purchase that should get a budget line going forward, or money that was clearly meant to come from a different category - mention it, but don't assume which.
- **`credit_card_overspent`** - negative available in a Credit Card Payments category. This means more was charged on that card than YNAB has set aside to pay it off, which is worth flagging distinctly from regular overspending since the fix (move money from the spending category that caused it, or from savings) is different from "spend less."
- **`hidden_categories_with_activity`** - categories the user has hidden in YNAB that still show assigned or spent amounts. Usually worth a quick mention since the user may not think to check hidden categories - could be a forgotten recurring charge or a category that should be unhidden.
- **`totals`** and **`group_totals`** - overall and per-category-group assigned/activity/available. Use these to give the high-level shape of the month (which groups absorbed the most spending) before drilling into individual categories.
- **`top_spending_categories`** - the biggest spend categories this month (by dollar amount, not just overspent ones), each with `activity_history` for the prior months and `pct_change_vs_history_average` - positive means spent more than typical, negative means less. Use this when the user asks what they spent the most on or how it compares to the past. A category with no history (new this month) has `pct_change_vs_history_average: null` - say it's new rather than computing a bogus percentage.

**Comparing to the past, mid-month:** if the target month is still in progress (check whether it's the current calendar month), lower spending than average for a given category may just mean the month isn't over yet, not that spending actually dropped - mention that caveat rather than reading a partial month as a real trend.

## Tone

This is someone's personal finances - keep the summary matter-of-fact and non-judgmental. State what happened and what it means for next month's budget; skip commentary on whether their spending choices were good or bad. If everything is healthy (no overspending, nothing running low), say so plainly and briefly rather than manufacturing concerns to fill out a report.
