import re
from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal, ROUND_HALF_UP
from statistics import median
from collections import defaultdict

from fastapi import HTTPException
from sqlalchemy import case, func, or_

from app.models.finance import Bill, Expense, Payment
from app.schemas.finance_analytics import FinanceReport


FINANCE_ROLES = ("admin", "staff")
IST = timezone(timedelta(hours=5, minutes=30), "IST")
ONE_DAY = timedelta(days=1)
ZERO = Decimal("0")
CENT = Decimal("0.01")
COLLECTIONS = "Collections are completed payments grouped by payment date."
EXPENSES = "Expenses are recorded amounts grouped by expense date."
MOVEMENT = "Recorded financial movement is collections minus recorded expenses."


def finance_today():
    return datetime.now(IST).date()


def payment_boundary(db, day):
    return reporting_timestamp(db, datetime.combine(day, time.min, IST))


def reporting_timestamp(db, value):
    boundary = value.astimezone(timezone.utc)
    # SQLite stores application payment timestamps as naive UTC.
    return boundary.replace(tzinfo=None) if db.get_bind().dialect.name == "sqlite" else boundary


def _month(day, offset=0):
    year, month = divmod(day.year * 12 + day.month - 1 + offset, 12)
    return date(year, month + 1, 1)


def _money(value):
    return Decimal(str(value if value is not None else 0)).quantize(CENT, rounding=ROUND_HALF_UP)


def _payments(db):
    return db.query(Payment).filter(Payment.payment_status == "Completed")


def amount_series(db, periods, *, expenses=False):
    if not periods:
        return [], 0
    if expenses:
        query, stamp, amount = db.query(Expense), Expense.expense_date, Expense.amount
        bounds = periods
    else:
        query, stamp, amount = _payments(db), Payment.paid_at, Payment.amount
        bounds = [(payment_boundary(db, start), payment_boundary(db, end)) for start, end in periods]
    ranges = [(stamp >= start) & (stamp < end) for start, end in bounds]
    totals = query.filter(stamp >= min(start for start, _ in bounds), stamp < max(end for _, end in bounds)).with_entities(
        *(func.sum(case((bounds_match, amount), else_=0)) for bounds_match in ranges),
        func.count(case((or_(*ranges), 1))),
    ).one()
    return [_money(value) for value in totals[:-1]], totals[-1]


def recorded_total(db, start=None, end=None, *, expenses=False, through=None, patient_id=None):
    if expenses:
        query, stamp, amount = db.query(Expense), Expense.expense_date, Expense.amount
    else:
        query, stamp, amount = _payments(db), Payment.paid_at, Payment.amount
        if patient_id is not None:
            query = query.join(Bill).filter(Bill.patient_id == patient_id)
        start = payment_boundary(db, start) if start else None
        end = payment_boundary(db, end) if end else None
        if through is not None:
            query = query.filter(stamp <= reporting_timestamp(db, through))
    if start:
        query = query.filter(stamp >= start)
    if end:
        query = query.filter(stamp < end)
    return _money(query.with_entities(func.sum(amount)).scalar())


def bill_balances(db, cutoff=None, *, patient_id=None):
    payments = _payments(db)
    bills = db.query(Bill).filter(Bill.status != "Cancelled")
    if patient_id is not None:
        bills = bills.filter(Bill.patient_id == patient_id)
    if cutoff:
        boundary = payment_boundary(db, cutoff)
        payments = payments.filter(Payment.paid_at < boundary)
        bills = bills.filter(Bill.created_at < boundary)
    applied = payments.with_entities(Payment.bill_id, func.sum(Payment.amount).label("paid")).group_by(Payment.bill_id).subquery()
    paid = func.coalesce(applied.c.paid, 0)
    due = case((Bill.total_amount > paid, Bill.total_amount - paid), else_=0)
    rows = bills.outerjoin(applied, Bill.id == applied.c.bill_id).with_entities(
        func.sum(Bill.total_amount - due),
        func.sum(due),
        func.sum(case(((due > 0) & (paid == 0), 1), else_=0)),
        func.sum(case(((due > 0) & (paid > 0), 1), else_=0)),
        func.count(Bill.id),
    ).one()
    return {"paid": _money(rows[0]), "outstanding": _money(rows[1]), "unpaid": rows[2] or 0,
            "partial": rows[3] or 0, "count": rows[4]}


def _chart(title, kind, labels, activity, **series):
    return {"title": title, "kind": kind, "labels": labels, "has_activity": bool(activity),
            "series": [{"label": label.replace("_", " "), "values": values} for label, values in series.items()]}


def _metric(label, value, unit="INR"):
    return {"label": label, "value": value, "unit": unit}


def _change(label, current, previous):
    difference = current - previous
    percentage = _money(difference / previous * 100) if previous else None
    return [_metric(f"{label} change", difference), _metric(f"{label} change (%)", percentage, "percent")]


def _comparison(db, today, quarterly):
    months = 3 if quarterly else 1
    current = _month(today, -((today.month - 1) % 3) if quarterly else 0)
    previous = _month(current, -months)
    elapsed = min((today - current).days, (current - previous).days)
    periods = [(current, current + timedelta(days=elapsed)), (previous, previous + timedelta(days=elapsed))]
    collections, payment_count = amount_series(db, periods)
    expenses, expense_count = amount_series(db, periods, expenses=True)
    metrics = _change("Collections", *collections) + _change("Expenses", *expenses)
    period_label = "quarter" if quarterly else "month"
    notes = [COLLECTIONS, EXPENSES, "Uses equal numbers of completed calendar days. Today is excluded.",
             "Percentage changes are unavailable when the previous period is zero."]
    if not elapsed:
        notes.append("No comparable complete days have elapsed yet.")
    labels = [
        f"{start.isoformat()} to {(end - ONE_DAY).isoformat()}" if elapsed else f"{start.isoformat()} (0 days)"
        for start, end in periods
    ]
    return FinanceReport(
        title=f"Current {period_label} versus previous {period_label}",
        start_date=previous, end_date=today - ONE_DAY, notes=notes, metrics=metrics,
        charts=[_chart("Collections and recorded expenses", "bar", labels, payment_count or expense_count,
                       Collections=collections, Expenses=expenses)],
    )


def _category_report(db, today):
    start = _month(today)
    rows = db.query(Expense.category, func.sum(Expense.amount)).filter(
        Expense.expense_date >= start, Expense.expense_date <= today,
    ).group_by(Expense.category).order_by(func.sum(Expense.amount).desc(), Expense.category).all()
    labels, values = [row[0] for row in rows[:19]], [_money(row[1]) for row in rows[:19]]
    if len(rows) > 19:
        labels.append("Remaining categories")
        values.append(sum((_money(row[1]) for row in rows[19:]), ZERO))
    return FinanceReport(title="Expense categories", start_date=start, end_date=today, notes=[EXPENSES],
                         metrics=[_metric("Total recorded expenses", sum(values, ZERO))]
                         + ([_metric(f"Highest category · {labels[0]}", values[0])] if labels else []),
                         charts=[_chart("Recorded expenses by category", "bar", labels, rows, Expenses=values)])


def _unusual_report(db, today):
    start = today - timedelta(days=29)
    baseline = start - timedelta(days=180)
    samples = defaultdict(list)
    for category, amount in db.query(Expense.category, Expense.amount).filter(
        Expense.expense_date >= baseline, Expense.expense_date < start,
    ):
        samples[category].append(amount)
    thresholds = {category: median(values) * 3 for category, values in samples.items() if len(values) >= 8 and median(values) > 0}
    candidates = []
    recent_count = assessed = 0
    for category, amount, day in db.query(Expense.category, Expense.amount, Expense.expense_date).filter(
        Expense.expense_date >= start, Expense.expense_date <= today,
    ).order_by(Expense.amount.desc(), Expense.expense_date.desc(), Expense.id):
        recent_count += 1
        if category in thresholds:
            assessed += 1
            if amount > thresholds[category]:
                candidates.append(_metric(f"{day} · {category} · threshold ₹{thresholds[category]:,.2f} (n={len(samples[category])})", amount))
    return FinanceReport(
        title="Unusual expense candidates", start_date=start, end_date=today,
        notes=[f"Flags records above 3× their category median from the prior 180 days ({baseline} to {start - ONE_DAY}).",
               "Each category needs at least 8 historical records and a positive median. Candidates require review.",
               f"Reviewed {assessed} of {recent_count} recent records. Showing up to 20 candidates."],
        metrics=[_metric("Candidates", len(candidates) if assessed else None, "count"), *candidates[:20]],
    )


def _forecast(db, today):
    periods = [(_month(today, index), _month(today, index + 1)) for index in range(-6, 0)]
    totals, _ = amount_series(db, periods)
    target = _month(today, 1)
    target_end = _month(today, 2) - ONE_DAY
    enough = all(value > ZERO for value in totals)
    return FinanceReport(
        title="Next-month collections forecast", start_date=target, end_date=target_end,
        notes=[f"Historical window: {periods[0][0]} to {periods[-1][1] - ONE_DAY}. Cutoff: {periods[-1][1] - ONE_DAY}.",
               "Horizon: one calendar month. Baseline: mean of six completed calendar months with positive collections.",
               "Assumes the recent level continues. No adjustment for seasonality or future events.",
               "Forecast unavailable because one or more historical months lacks positive recorded collections." if not enough
               else "This estimate assumes historical recording is representative."],
        metrics=[_metric("Baseline forecast", _money(sum(totals, ZERO) / len(totals)) if enough else None)],
    )


def _series_report(db, today, view, grain, months, start_date, end_date):
    stop = min(date.fromisoformat(end_date), today) + ONE_DAY if end_date else today + ONE_DAY
    start = date.fromisoformat(start_date) if start_date else (
        _month(today, 1 - months) if grain == "monthly" else today - timedelta(days=27 if grain == "daily" else 83)
    )
    if start >= stop or (stop - start).days > (90 if grain == "daily" else 366):
        raise ValueError("Choose an ordered date range within the supported reporting window.")
    periods = []
    cursor = start
    while cursor < stop:
        boundary = _month(cursor, 1) if grain == "monthly" else (
            cursor + timedelta(days=7 - cursor.weekday()) if grain == "weekly" else cursor + ONE_DAY
        )
        end = min(stop, boundary)
        periods.append((cursor, end))
        cursor = end
    if grain == "monthly" and len(periods) > 12:
        raise ValueError("Choose a range spanning no more than 12 calendar months.")
    labels = [day.strftime("%b %Y") if grain == "monthly" and day.day == 1 else day.isoformat() for day, _ in periods]
    wants_collections = view != "expenses"
    wants_expenses = view != "collections"
    collections, payment_count = amount_series(db, periods) if wants_collections else ([], 0)
    expenses, expense_count = amount_series(db, periods, expenses=True) if wants_expenses else ([], 0)
    metrics, charts, notes = [], [], ["Zero indicates no amount recorded in that bucket. The latest bucket may be partial."]
    if wants_collections:
        notes.append(COLLECTIONS)
        metrics.append(_metric("Total completed collections", sum(collections, ZERO)))
        if payment_count and view == "collections":
            highest = collections.index(max(collections))
            lowest = collections.index(min(collections))
            metrics.extend([_metric(f"Highest collection period · {labels[highest]}", collections[highest]),
                            _metric(f"Lowest collection period · {labels[lowest]}", collections[lowest])])
        if view == "collections":
            charts.append(_chart("Completed collection trend", "line", labels, payment_count, Collections=collections))
    if wants_expenses:
        notes.append(EXPENSES)
        metrics.append(_metric("Total recorded expenses", sum(expenses, ZERO)))
        if view == "expenses":
            charts.append(_chart("Recorded expense trend", "line", labels, expense_count, Expenses=expenses))
    if wants_collections and wants_expenses:
        movement = [incoming - outgoing for incoming, outgoing in zip(collections, expenses)]
        total_movement = sum(movement, ZERO)
        relationship = "exceeded" if total_movement > 0 else "were below" if total_movement < 0 else "matched"
        notes.append(MOVEMENT)
        if payment_count or expense_count:
            notes.append(f"Completed collections {relationship} recorded expenses over this period.")
        metrics.append(_metric("Recorded financial movement", total_movement))
        charts.extend([
            _chart("Collections versus recorded expenses", "bar", labels, payment_count or expense_count,
                   Collections=collections, Expenses=expenses),
            _chart("Recorded financial movement trend", "line", labels, payment_count or expense_count, Movement=movement),
        ])
    return FinanceReport(title="Financial activity" if view == "performance" else charts[0]["title"],
                         start_date=start, end_date=stop - ONE_DAY, notes=notes, metrics=metrics, charts=charts)


def finance_analytics(db, user, view="performance", grain="monthly", months=6, start_date=None, end_date=None):
    if user.role not in FINANCE_ROLES:
        raise HTTPException(status_code=403, detail="Finance access is required")
    today = finance_today()
    try:
        if view in ("month_comparison", "quarter_comparison"):
            report = _comparison(db, today, view == "quarter_comparison")
        elif view == "balances":
            balances = bill_balances(db, today + ONE_DAY)
            report = FinanceReport(
                title="Paid and outstanding bill balances", end_date=today,
                notes=["Snapshot of non-cancelled bills. Applied amounts use completed payments, capped at each bill’s face value."],
                metrics=[_metric("Paid amount applied", balances["paid"]), _metric("Outstanding amount", balances["outstanding"]),
                         _metric("Unpaid bills", balances["unpaid"], "count"), _metric("Partially paid bills", balances["partial"], "count")],
                charts=[_chart("Paid versus outstanding", "bar", ["Paid", "Outstanding"], balances["count"],
                               Amount=[balances["paid"], balances["outstanding"]])],
            )
        elif view == "categories":
            report = _category_report(db, today)
        elif view == "unusual":
            report = _unusual_report(db, today)
        elif view == "forecast":
            report = _forecast(db, today)
        elif view == "department":
            report = FinanceReport(title="Department expense reporting unavailable", end_date=today,
                                   notes=["Recorded expenses have category attribution. Department attribution is unavailable."])
        elif view in ("performance", "collections", "expenses") and grain in ("daily", "weekly", "monthly") and 1 <= months <= 12:
            report = _series_report(db, today, view, grain, months, start_date, end_date)
        else:
            raise ValueError("Choose a supported report, granularity and a range of up to 12 months.")
    except (ValueError, OverflowError) as error:
        return {"status": "error", "message": str(error)}
    return {"message": report.title, "finance_report": report.model_dump(mode="json")}


def finance_intent(query):
    text = query.lower()
    if re.search(r"\b(generate|create|issue|record|pay|refund|delete|update|cancel)\b", text) and "summary" not in text and "report" not in text:
        return None
    if "forecast" in text and re.search(r"\b(collections?|revenue)\b", text):
        return {"view": "forecast"}
    if "expense" in text and "department" in text:
        return {"view": "department"}
    if re.search(r"\b(unusual|anomal(?:y|ies))\b", text) and "expense" in text:
        return {"view": "unusual"}
    if "quarter" in text and re.search(r"compar|financial|revenue|expense|collection", text):
        return {"view": "quarter_comparison"}
    if ("last month" in text and "this month" in text) or "month-over-month" in text:
        return {"view": "month_comparison"}
    if re.search(r"\b(outstanding|partially paid|unpaid|paid versus)\b", text) and re.search(r"bill|payment|balance|amount", text):
        return {"view": "balances"}
    if "expense" in text and re.search(r"categor|breakdown|costs us the most", text):
        return {"view": "categories"}
    revenue = re.search(r"\b(revenue|collections?)\b", text)
    expenses = "expense" in text
    if not (revenue or expenses or re.search(r"financial (?:performance|movement|summary|trend|report|kpi)", text)):
        return None
    view = "performance" if (revenue and expenses) or not (revenue or expenses) else "collections" if revenue else "expenses"
    grain = "daily" if re.search(r"\b(daily|today)\b", text) else "weekly" if "weekly" in text else "monthly"
    duration = re.search(r"\blast\s+(\d{1,2})\s+months\b", text)
    args = {"view": view, "grain": grain, "months": int(duration[1]) if duration else 6}
    explicit_dates = re.findall(r"\b\d{4}-\d{2}-\d{2}\b", text)
    if len(explicit_dates) == 2:
        args.update(start_date=explicit_dates[0], end_date=explicit_dates[1])
    elif "this month" in text:
        args.update(months=1, start_date=_month(finance_today()).isoformat())
    elif "last month" in text:
        today = finance_today()
        args.update(start_date=_month(today, -1).isoformat(), end_date=(_month(today) - ONE_DAY).isoformat())
    elif re.search(r"\btoday\b", text):
        day = finance_today().isoformat()
        args.update(start_date=day, end_date=day)
    return args
