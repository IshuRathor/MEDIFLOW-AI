def support_agent(user_query: str):
    """
    Handles customer support-related queries for MEDIFLOW AI.
    """

    query = user_query.lower().strip()

    # ============================================================
    # GENERAL HELP
    # ============================================================

    if (
        "help" in query
        or "how can you help" in query
        or "what can you help" in query
        or "what can you do" in query
    ):
        return {
            "agent": "Customer Support Agent",
            "category": "General Help",
            "message": (
                "I can help you with MEDIFLOW AI hospital management "
                "services. You can ask about appointments, doctors, "
                "doctor availability, hospital services, billing, "
                "payments, or general system support."
            )
        }

    # ============================================================
    # APPOINTMENT SUPPORT
    # ============================================================

    if (
        "appointment problem" in query
        or "appointment issue" in query
        or "appointment help" in query
        or "problem with my appointment" in query
        or "problem with the appointment" in query
        or "problem with appointment" in query
        or "issue with my appointment" in query
        or "issue with the appointment" in query
        or "issue with appointment" in query
        or "problem with my booking" in query
        or "problem with the booking" in query
        or "issue with my booking" in query
        or "issue with the booking" in query
        or "booking problem" in query
        or "booking issue" in query
        or "booking help" in query
    ):
        return {
            "agent": "Customer Support Agent",
            "category": "Appointment Support",
            "message": (
                "I can help with appointment-related support. "
                "You can ask the Hospital Agent to check doctors, "
                "availability, appointment slots, or appointment booking."
            )
        }

    # ============================================================
    # DOCTOR SUPPORT
    # ============================================================

    if (
        "doctor problem" in query
        or "doctor issue" in query
        or "doctor help" in query
        or "problem with my doctor" in query
        or "issue with my doctor" in query
    ):
        return {
            "agent": "Customer Support Agent",
            "category": "Doctor Support",
            "message": (
                "For doctor-related information, you can ask about "
                "available doctors, their specialization, working "
                "hours, or appointment availability."
            )
        }

    # ============================================================
    # BILLING / PAYMENT SUPPORT
    # ============================================================

    if (
        "billing problem" in query
        or "billing issue" in query
        or "bill problem" in query
        or "bill issue" in query
        or "problem with my bill" in query
        or "issue with my bill" in query
        or "payment problem" in query
        or "payment issue" in query
        or "payment help" in query
        or "problem with my payment" in query
        or "issue with my payment" in query
    ):
        return {
            "agent": "Customer Support Agent",
            "category": "Finance Support",
            "message": (
                "For billing and payment-related information, "
                "please ask about bills, payments, revenue, expenses, "
                "or financial records."
            )
        }

    # ============================================================
    # TECHNICAL SUPPORT
    # ============================================================

    if (
        "technical problem" in query
        or "technical issue" in query
        or "system problem" in query
        or "system issue" in query
        or "technical error" in query
        or "system error" in query
        or "error" in query
        or "not working" in query
    ):
        return {
            "agent": "Customer Support Agent",
            "category": "Technical Support",
            "message": (
                "Please describe the technical problem or error "
                "you are experiencing. Include the relevant screen, "
                "operation, or error message if available."
            )
        }

    # ============================================================
    # COMPLAINT
    # ============================================================

    if (
        "complaint" in query
        or "complain" in query
        or "unhappy" in query
        or "dissatisfied" in query
    ):
        return {
            "agent": "Customer Support Agent",
            "category": "Complaint",
            "message": (
                "I'm sorry you are experiencing an issue. "
                "Please describe your complaint clearly so it "
                "can be reviewed and handled appropriately."
            )
        }

    # ============================================================
    # GENERAL PROBLEM / ISSUE
    # ============================================================

    if (
        "problem" in query
        or "issue" in query
        or "trouble" in query
    ):
        return {
            "agent": "Customer Support Agent",
            "category": "General Support",
            "message": (
                "Please describe the problem you are experiencing. "
                "I will help identify the appropriate MEDIFLOW AI "
                "service or next step."
            )
        }

    # ============================================================
    # SUPPORT
    # ============================================================

    if "support" in query:
        return {
            "agent": "Customer Support Agent",
            "category": "General Support",
            "message": (
                "I can provide support for MEDIFLOW AI services, "
                "including appointments, doctors, hospital operations, "
                "billing, payments, and general system issues."
            )
        }

    # ============================================================
    # DEFAULT
    # ============================================================

    return {
        "agent": "Customer Support Agent",
        "category": "General Support",
        "message": (
            "I can help with MEDIFLOW AI system support. "
            "Please describe what you need help with."
        )
    }