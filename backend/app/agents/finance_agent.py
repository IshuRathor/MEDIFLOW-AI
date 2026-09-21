from sqlalchemy import func

from app.database.db import SessionLocal
from app.models.finance import Bill, Payment, Expense


def finance_agent(user_query: str):
    """
    Handles finance-related queries using real PostgreSQL data.
    """

    query = user_query.lower()

    db = SessionLocal()

    try:

        # =====================================================
        # FINANCIAL SUMMARY
        # =====================================================

        if (
            "financial summary" in query
            or "finance summary" in query
            or "financial report" in query
            or "finance report" in query
            or "overall financial" in query
        ):

            total_revenue = (
                db.query(func.coalesce(func.sum(Payment.amount), 0))
                .filter(Payment.payment_status == "Completed")
                .scalar()
            )

            total_expenses = (
                db.query(func.coalesce(func.sum(Expense.amount), 0))
                .scalar()
            )

            completed_payments = (
                db.query(Payment)
                .filter(Payment.payment_status == "Completed")
                .count()
            )

            pending_bills = (
                db.query(Bill)
                .filter(Bill.status == "Pending")
                .all()
            )

            revenue = float(total_revenue)
            expenses = float(total_expenses)
            net_income = revenue - expenses

            pending_amount = sum(
                float(bill.total_amount)
                for bill in pending_bills
            )

            return {
                "agent": "Finance Agent",
                "metric": "Financial Summary",
                "revenue": revenue,
                "expenses": expenses,
                "net_income": net_income,
                "completed_payments": completed_payments,
                "pending_bills": len(pending_bills),
                "pending_amount": pending_amount,
                "currency": "INR",
                "message": (
                    f"Financial Summary: Revenue ₹{revenue:,.2f}, "
                    f"Expenses ₹{expenses:,.2f}, "
                    f"Net Income ₹{net_income:,.2f}, "
                    f"{completed_payments} completed payments, "
                    f"{len(pending_bills)} pending bills worth "
                    f"₹{pending_amount:,.2f}."
                )
            }


        # =====================================================
        # NET INCOME
        # =====================================================

        if "net income" in query or "profit" in query:

            total_revenue = (
                db.query(func.coalesce(func.sum(Payment.amount), 0))
                .filter(Payment.payment_status == "Completed")
                .scalar()
            )

            total_expenses = (
                db.query(func.coalesce(func.sum(Expense.amount), 0))
                .scalar()
            )

            revenue = float(total_revenue)
            expenses = float(total_expenses)
            net_income = revenue - expenses

            return {
                "agent": "Finance Agent",
                "metric": "Net Income",
                "revenue": revenue,
                "expenses": expenses,
                "net_income": net_income,
                "currency": "INR",
                "message": (
                    f"Net hospital income is ₹{net_income:,.2f} "
                    f"(Revenue ₹{revenue:,.2f} "
                    f"- Expenses ₹{expenses:,.2f})."
                )
            }


        # =====================================================
        # TOTAL REVENUE
        # =====================================================

        if "revenue" in query:

            total_revenue = (
                db.query(func.coalesce(func.sum(Payment.amount), 0))
                .filter(Payment.payment_status == "Completed")
                .scalar()
            )

            revenue = float(total_revenue)

            return {
                "agent": "Finance Agent",
                "metric": "Total Revenue",
                "amount": revenue,
                "currency": "INR",
                "message": f"Total hospital revenue is ₹{revenue:,.2f}."
            }


        # =====================================================
        # TOTAL INCOME
        # =====================================================

        if "income" in query:

            total_revenue = (
                db.query(func.coalesce(func.sum(Payment.amount), 0))
                .filter(Payment.payment_status == "Completed")
                .scalar()
            )

            income = float(total_revenue)

            return {
                "agent": "Finance Agent",
                "metric": "Total Income",
                "amount": income,
                "currency": "INR",
                "message": f"Total hospital income is ₹{income:,.2f}."
            }


        # =====================================================
        # TOTAL EXPENSES
        # =====================================================

        if "expense" in query or "expenses" in query:

            total_expenses = (
                db.query(func.coalesce(func.sum(Expense.amount), 0))
                .scalar()
            )

            expenses = float(total_expenses)

            return {
                "agent": "Finance Agent",
                "metric": "Total Expenses",
                "amount": expenses,
                "currency": "INR",
                "message": f"Total hospital expenses are ₹{expenses:,.2f}."
            }


        # =====================================================
        # PENDING BILLS
        # =====================================================

        if "pending bill" in query or "pending bills" in query:

            pending_bills = (
                db.query(Bill)
                .filter(Bill.status == "Pending")
                .all()
            )

            bill_list = []

            for bill in pending_bills:
                bill_list.append({
                    "id": bill.id,
                    "bill_number": bill.bill_number,
                    "patient_id": bill.patient_id,
                    "total_amount": float(bill.total_amount),
                    "status": bill.status
                })

            total_pending = sum(
                bill["total_amount"]
                for bill in bill_list
            )

            return {
                "agent": "Finance Agent",
                "metric": "Pending Bills",
                "count": len(bill_list),
                "total_pending_amount": total_pending,
                "currency": "INR",
                "bills": bill_list,
                "message": (
                    f"There are {len(bill_list)} pending bills "
                    f"worth ₹{total_pending:,.2f}."
                )
            }


        # =====================================================
        # BILLING
        # =====================================================

        if "bill" in query or "billing" in query:

            total_bills = db.query(Bill).count()

            return {
                "agent": "Finance Agent",
                "metric": "Billing",
                "total_bills": total_bills,
                "message": (
                    f"The hospital currently has "
                    f"{total_bills} bills."
                )
            }


        # =====================================================
        # PAYMENTS
        # =====================================================

        if "payment" in query or "payments" in query:

            total_payments = (
                db.query(func.coalesce(func.sum(Payment.amount), 0))
                .filter(Payment.payment_status == "Completed")
                .scalar()
            )

            payment_count = (
                db.query(Payment)
                .filter(Payment.payment_status == "Completed")
                .count()
            )

            amount = float(total_payments)

            return {
                "agent": "Finance Agent",
                "metric": "Payments",
                "payment_count": payment_count,
                "total_amount": amount,
                "currency": "INR",
                "message": (
                    f"There are {payment_count} completed payments "
                    f"totalling ₹{amount:,.2f}."
                )
            }


        # =====================================================
        # DEFAULT RESPONSE
        # =====================================================

        return {
            "agent": "Finance Agent",
            "message": (
                "I can help with revenue, income, expenses, "
                "net income, financial summary, billing, "
                "pending bills and payments."
            )
        }

    finally:
        db.close()