import re
from datetime import date, datetime, time, timedelta, timezone

from fastapi import HTTPException
from sqlalchemy import case, func

from app.models.appointment import Appointment
from app.models.doctor import Doctor
from app.models.patient import Patient
from app.models.user import User
from app.schemas.admin_analytics import AdminReport
from app.services.cancellation import PENDING_CANCELLATION
from app.services.finance_analytics import IST, payment_boundary, recorded_total, reporting_timestamp


DAY = timedelta(days=1)
RANK_LIMIT = 15
BOOKING_PENDING = "Pending Doctor Approval"
STATUSES = (BOOKING_PENDING, "Scheduled", "Completed", "Cancelled", "Declined", "No-show")
VIEWS = {
    "overview": "Hospital executive overview",
    "report": "Hospital performance report",
    "demand": "Monthly appointment demand",
    "appointments": "Monthly appointment volumes",
    "status": "Appointment status distribution",
    "cancellations": "Recorded cancellation activity",
    "departments": "Doctors by current department",
    "department_volume": "Appointment volume by current department",
    "doctor_volume": "Recorded appointment workload by doctor",
    "queues": "Pending operational queues",
    "account_queue": "Pending account approvals",
    "booking_queue": "Pending booking requests",
    "cancellation_queue": "Pending cancellation requests",
    "limitations": "Hospital metrics that require additional records",
}
LIMITATIONS = (
    "Bed and occupancy metrics require bed, admission and discharge records. "
    "Actual waiting times and throughput require check-in and service-start timestamps and encounter records. "
    "Staffing shortages and historical utilization require rosters and historical offered-capacity snapshots. "
    "Department profitability requires expense cost-center and revenue attribution. "
    "Booking conversion, rejected demand and historical no-show rates require complete intake and appointment lifecycle events."
)


def _report_now():
    return datetime.now(IST)


def _month_start(day, offset=0):
    year, month = divmod(day.year * 12 + day.month - 1 + offset, 12)
    return date(year, month + 1, 1)


def _period(today, view, start_date, end_date):
    end = date.fromisoformat(end_date) if end_date else today
    months = 6 if view in ("report", "demand", "appointments", "cancellations") else 1
    start = date.fromisoformat(start_date) if start_date else _month_start(end, 1 - months)
    month_count = (end.year - start.year) * 12 + end.month - start.month + 1
    if start > end or end > today or (end - start).days >= 366 or month_count > 12:
        raise ValueError("Choose an ordered range of up to 12 calendar months ending no later than today.")
    return start, end


def _visit_stamp(db, value):
    # SQLite booking stores browser-selected visit times as local wall times.
    return value.replace(tzinfo=None) if db.get_bind().dialect.name == "sqlite" else reporting_timestamp(db, value)


def _in_period(db, column, start, end):
    if column is Appointment.appointment_date:
        lower = _visit_stamp(db, datetime.combine(start, time.min, IST))
        upper = _visit_stamp(db, datetime.combine(end + DAY, time.min, IST))
    else:
        lower, upper = payment_boundary(db, start), payment_boundary(db, end + DAY)
    return (column >= lower) & (column < upper)


def _period_count(db, query, column, start, end, cutoff=None):
    query = query.filter(_in_period(db, column, start, end))
    if cutoff is not None:
        query = query.filter(column <= reporting_timestamp(db, cutoff))
    return query.count()


def _count(label, value):
    return {"label": label, "value": value, "unit": "count"}


def _chart(title, labels, series, kind="bar"):
    return {
        "title": title, "kind": kind, "labels": labels, "unit": "count",
        "series": [{"label": label, "values": values} for label, values in series.items()],
        "has_activity": any(any(values) for values in series.values()),
    }


def _months(db, query, column, start, end, cutoff=None):
    months = []
    cursor = start
    while cursor <= end:
        boundary = min(_month_start(cursor, 1), end + DAY)
        months.append(_in_period(db, column, cursor, boundary - DAY))
        cursor = boundary
    query = query.filter(_in_period(db, column, start, end))
    if cutoff is not None:
        query = query.filter(column <= reporting_timestamp(db, cutoff))
    return list(query.with_entities(*(func.count(case((predicate, 1))) for predicate in months)).one())


def _timeline(report, db, view, start, end, cutoff):
    visits = db.query(Appointment)
    labels = []
    cursor = _month_start(start)
    while cursor <= end:
        labels.append(cursor.strftime("%b %Y"))
        cursor = _month_start(cursor, 1)
    if view == "cancellations":
        requests = _months(db, visits, Appointment.cancellation_requested_at, start, end, cutoff)
        cancelled = _months(db, visits.filter(Appointment.status == "Cancelled"), Appointment.appointment_date, start, end)
        report["metrics"].extend([_count("Recorded latest cancellation requests", sum(requests)),
                                  _count("Appointments currently cancelled", sum(cancelled))])
        report["charts"].append(_chart("Recorded cancellation activity", labels, {
            "Latest requests by request date": requests,
            "Currently cancelled by appointment date": cancelled,
        }, "line"))
        report["notes"].append("Requests use Appointment.cancellation_requested_at. Only the latest retained request per appointment is counted. Cancelled appointments use Appointment.appointment_date and current status. Decision dates and complete request history are unavailable.")
        return
    created = _months(db, visits, Appointment.created_at, start, end, cutoff)
    dated = _months(db, visits, Appointment.appointment_date, start, end)
    if view in ("demand", "appointments"):
        report["metrics"].extend([_count("Recorded appointment creations", sum(created)),
                                  _count("Appointments by visit date", sum(dated))])
    report["charts"].append(_chart("Monthly appointment activity", labels, {
        "Records created": created, "Appointments by visit date": dated,
    }, "line"))
    report["notes"].append("Demand is proxied by recorded Appointment.created_at. Visit volumes use Appointment.appointment_date and include all statuses. An incomplete month may have fewer records. The database cannot reconstruct unmet demand or historical conversion or no-show rates.")


def _status_chart(db, start, end):
    status = case((Appointment.status.in_(STATUSES), Appointment.status), else_="Other recorded status")
    counts = dict(db.query(status, func.count(Appointment.id))
                  .filter(_in_period(db, Appointment.appointment_date, start, end))
                  .group_by(status).all())
    other = counts.get("Other recorded status", 0)
    labels = [*STATUSES, "Other recorded status"] if other else list(STATUSES)
    values = [counts.get(status, 0) for status in STATUSES] + ([other] if other else [])
    return _chart("Current status of appointments in the period", labels, {"Appointments": values})


def _rank_chart(db, view, start, end):
    department = func.coalesce(func.nullif(func.trim(Doctor.department), ""), "Unassigned")
    if view == "departments":
        records = db.query(Doctor)
        count, label, group = func.count(Doctor.id), department, (department,)
        title, series = "Registered doctors by current department", "Doctors"
    else:
        records = db.query(Appointment).join(Doctor, Appointment.doctor_id == Doctor.id).filter(
            _in_period(db, Appointment.appointment_date, start, end)
        )
        count = func.count(Appointment.id)
        label, group = (department, (department,)) if view == "department_volume" else (Doctor.name, (Doctor.id, Doctor.name))
        title = "Appointments by current doctor department" if view == "department_volume" else "Appointments by doctor"
        series = "Appointments"
    rows = records.with_entities(label, count).group_by(*group).order_by(count.desc(), *group).limit(RANK_LIMIT).all()
    labels, values = [name for name, _ in rows], [value for _, value in rows]
    remaining = records.count() - sum(values)
    if remaining:
        labels.append("Remaining groups")
        values.append(remaining)
    return _chart(title, labels, {series: values})


def _queues(db, cutoff, view):
    instant = reporting_timestamp(db, cutoff)
    one_day = instant - DAY
    seven_days = instant - 7 * DAY
    specifications = {
        "account_queue": ("Account approvals", User, User.approval_status == "pending", User.created_at, "User.created_at", "pending"),
        "booking_queue": ("Booking requests", Appointment, Appointment.status == BOOKING_PENDING, Appointment.created_at, "Appointment.created_at", BOOKING_PENDING),
        "cancellation_queue": ("Cancellation requests", Appointment, Appointment.cancellation_status == PENDING_CANCELLATION,
                               Appointment.cancellation_requested_at, "Appointment.cancellation_requested_at", PENDING_CANCELLATION),
    }
    queues, bands, aged = [], {}, []
    for key, (title, model, predicate, stamp, source, status) in specifications.items():
        if view in specifications and key != view:
            continue
        valid = stamp <= instant
        total, oldest, recent, middle, old = db.query(
            func.count(model.id), func.min(case((valid, stamp))),
            func.count(case((valid & (stamp > one_day), 1))),
            func.count(case(((stamp <= one_day) & (stamp > seven_days), 1))),
            func.count(case((stamp <= seven_days, 1))),
        ).filter(predicate).one()
        if oldest is not None:
            oldest = (oldest if oldest.tzinfo else oldest.replace(tzinfo=timezone.utc)).astimezone(IST)
        queues.append({
            "title": title, "source": source, "status": status, "count": total, "oldest_at": oldest,
            "oldest_age_hours": int((cutoff - oldest).total_seconds() // 3600) if oldest is not None else None,
        })
        bands[title] = [recent, middle, old, total - recent - middle - old]
        if old:
            aged.append(f"{title}: {old} item(s) pending for at least seven days.")
    notes = [
        "Queue ages are measured from the recorded creation or request timestamp. Missing or future timestamps appear as unknown.",
        "Queue age is a review signal. It does not establish a service bottleneck or a patient wait time.",
    ]
    if aged:
        notes.append("Review the oldest entries first. " + " ".join(aged))
    elif any(queue["count"] for queue in queues):
        notes.append("Review the pending queues in the existing dashboards. No items with a known age reached seven days.")
    return queues, _chart("Pending queues by age", ["Under 1 day", "1–6 days", "7+ days", "Unknown"], bands), notes


def admin_analytics(db, user, view="overview", start_date=None, end_date=None):
    if user.role != "admin":
        raise HTTPException(status_code=403, detail="Administrator access is required")
    if view not in VIEWS:
        return {"status": "error", "message": "Choose a supported hospital intelligence report."}
    cutoff = _report_now()
    try:
        start, end = _period(cutoff.date(), view, start_date, end_date)
    except (ValueError, OverflowError):
        return {"status": "error", "message": "Use YYYY-MM-DD dates in an ordered range of up to 12 calendar months ending no later than today."}
    snapshot = view in ("queues", "account_queue", "booking_queue", "cancellation_queue", "departments", "limitations")
    if snapshot and (start_date or end_date):
        return {"status": "error", "message": "This view is a current snapshot. Use an appointment or performance report for a date range."}
    report = {"title": VIEWS[view], "start_date": None if snapshot else start, "end_date": cutoff.date() if snapshot else end,
              "cutoff": cutoff, "metrics": [], "charts": [], "queues": [], "notes": []}

    if view in ("overview", "report"):
        upcoming_end = cutoff.date() + 30 * DAY
        visits = db.query(Appointment)
        collections = recorded_total(db, start, end + DAY, through=cutoff)
        report["metrics"].extend([
            _count("Registered patients · current", db.query(Patient).count()),
            _count("Registered doctors · current", db.query(Doctor).count()),
            _count("Appointment records created in period", _period_count(db, visits, Appointment.created_at, start, end, cutoff)),
            _count("Appointments by visit date in period", _period_count(db, visits, Appointment.appointment_date, start, end)),
            _count("Upcoming scheduled appointments · next 30 days",
                   visits.filter(Appointment.status == "Scheduled", Appointment.appointment_date >= _visit_stamp(db, cutoff),
                                 Appointment.appointment_date < _visit_stamp(db, datetime.combine(upcoming_end, time.min, IST))).count()),
            _count("Pending account approvals · current", db.query(User).filter(User.approval_status == "pending").count()),
            {"label": "Completed collections in period", "value": collections, "unit": "INR"},
        ])
        report["notes"].extend([
            "Registration totals are current counts of Patient and Doctor records. Pending account approvals use current User.approval_status.",
            f"Upcoming counts use current Scheduled appointments from the cutoff to midnight at the start of {upcoming_end}.",
            "Collections reuse completed Payment.amount by paid_at through the selected IST end date. Review the Finance report for expenses and outstanding balances.",
        ])
    if view in ("overview", "report", "status"):
        report["charts"].append(_status_chart(db, start, end))
        report["notes"].append("Status distribution uses Appointment.appointment_date and the current Appointment.status, including all recorded statuses.")
    if view in ("overview", "report", "departments", "department_volume", "doctor_volume"):
        ranking = view if view in ("department_volume", "doctor_volume") else "departments"
        report["charts"].append(_rank_chart(db, ranking, start, end))
        report["notes"].append("Department classifications use current Doctor.department. Doctor and department appointment volumes count recorded visits by appointment date across statuses. The first 15 groups are shown individually.")
    if view in ("report", "demand", "appointments", "cancellations"):
        _timeline(report, db, view, start, end, cutoff)
    if view in ("report", "queues", "account_queue", "booking_queue", "cancellation_queue"):
        report["queues"], chart, notes = _queues(db, cutoff, view)
        report["charts"].append(chart)
        report["notes"].extend(notes)
    report["notes"].append("Zero means no qualifying records; it does not establish complete historical coverage.")
    if view in ("overview", "report", "doctor_volume", "department_volume", "limitations"):
        report["notes"].append(LIMITATIONS)
    return {"message": report["title"], "admin_report": AdminReport.model_validate(report).model_dump(mode="json")}


def admin_intent(query):
    words = query.lower().replace("’", "'")
    view = None
    if re.search(r"occupancy|bed availability|department profitability|historical utilization|working hours|waiting time|staffing shortage|patient throughput|no-show rate|booking conversion|rejected demand|unmet demand", words):
        view = "limitations"
    elif re.search(r"hospital performance report|this month's operations|operational concerns|management review", words):
        view = "report"
    elif re.search(r"hospital executive overview|hospital overview|overall hospital performance|hospital performing|summarize hospital operations", words):
        view = "overview"
    elif "pending" in words and "booking" in words and "cancellation" in words:
        view = "queues"
    elif re.search(r"pending operational queues|operational bottleneck|queues require attention|outstanding administrative work", words):
        view = "queues"
    elif re.search(r"pending (?:hospital|account|staff) approvals", words):
        view = "account_queue"
    elif re.search(r"pending (?:appointment|booking) requests", words):
        view = "booking_queue"
    elif "pending cancellation request" in words:
        view = "cancellation_queue"
    elif re.search(r"appointment status distribution", words):
        view = "status"
    elif re.search(r"appointment cancellations|cancellation[- ]request (?:analysis|trends)", words):
        view = "cancellations"
    elif "department" in words and re.search(r"appointment (?:volume|demand)|high demand", words):
        view = "department_volume"
    elif "department" in words and re.search(r"doctor (?:distribution|count)|doctors by|most doctors", words):
        view = "departments"
    elif re.search(r"appointment volumes? by doctor|doctor workload", words):
        view = "doctor_volume"
    elif "appointment demand" in words:
        view = "demand"
    elif re.search(r"appointment volumes? across months|hospital performance across months", words):
        view = "appointments"
    if not view:
        return None
    dates = re.findall(r"\b\d{4}-\d{2}-\d{2}\b", words)
    if len(dates) == 2:
        return {"view": view, "start_date": dates[0], "end_date": dates[1]}
    if view == "report" and "this month" in words:
        return {"view": view, "start_date": _month_start(_report_now().date()).isoformat()}
    return {"view": view}
