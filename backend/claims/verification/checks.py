"""The verification checks. Each check returns a list of finding dicts.

Hard rules (limits, dates, required documents) are deterministic Python so results are
repeatable and auditable. Retrieval is used to attach the exact policy wording as evidence.
"""
import re
from decimal import Decimal

from django.db.models import Sum
from django.utils import timezone
from rapidfuzz import fuzz

from policies import rag
from policies.applicability import detect_conflicts
from policies.models import DOCUMENT_LABELS

from .extraction import parse_iso

PRIMARY_TYPES = {"invoice", "bill", "receipt", "ticket", "medical_bill"}
DOC_EQUIVALENTS = {
    "invoice": {"invoice", "bill", "receipt", "ticket", "medical_bill"},
    "bill": {"bill", "receipt", "invoice"},
    "receipt": {"receipt", "bill", "invoice"},
    "ticket": {"ticket"},
    "payment_proof": {"payment_proof"},
    "approval": {"approval"},
    "medical_bill": {"medical_bill", "bill", "invoice"},
    "prescription": {"prescription"},
}


def money(value):
    return f"₹{Decimal(str(value)):,.2f}"


def norm_ref(value):
    return re.sub(r"[^A-Z0-9]", "", str(value or "").upper())


def excerpt(policy, topic):
    hits = rag.search(f"{policy.title} {topic}", policy_ids=[policy.id], top_k=1)
    return hits[0]["text"] if hits else policy.text[:400]


def finding(kind, severity, title, explanation, evidence=None, policy=None, policy_excerpt="", related_claim=None, document=None):
    return {
        "kind": kind, "severity": severity, "title": title, "explanation": explanation,
        "evidence": evidence or [], "policy": policy, "policy_excerpt": policy_excerpt,
        "related_claim": related_claim, "document": document,
    }


def _ev(label, value, source=""):
    return {"label": label, "value": str(value), "source": source}


# ----------------------------------------------------------------- claim basics

def check_claim_basics(claim, documents):
    out = []
    today = timezone.localdate()
    if claim.expense_date and claim.expense_date > today:
        out.append(finding("VIOLATION", "high", "Expense date is in the future",
                           f"The claim says the expense happened on {claim.expense_date:%d %b %Y}, which is after today.",
                           [_ev("Expense date", claim.expense_date), _ev("Today", today)]))
    if claim.start_date and claim.end_date and claim.end_date < claim.start_date:
        out.append(finding("MISSING_INFO", "medium", "Trip end date is before the start date",
                           "Correct the travel period so day and night limits can be calculated.",
                           [_ev("Start", claim.start_date), _ev("End", claim.end_date)]))
    if claim.category in ("travel", "accommodation") and not (claim.start_date and claim.end_date):
        out.append(finding("MISSING_INFO", "low", "Travel period not entered",
                           "Without start and end dates the system assumes a single day/night when applying limits."))
    if not claim.vendor:
        out.append(finding("MISSING_INFO", "low", "Vendor not entered", "Enter who was paid so invoices can be matched."))
    if not claim.invoice_number and claim.category != "food":
        out.append(finding("MISSING_INFO", "low", "Invoice number not entered",
                           "An invoice or bill number helps match documents and detect duplicates."))
    if not documents:
        out.append(finding("MISSING_DOCUMENT", "high", "No supporting documents uploaded",
                           "Every claim needs at least one invoice, bill, receipt or ticket."))
    for doc in documents:
        if doc.extraction_status in ("unreadable", "failed"):
            out.append(finding("UNREADABLE", "low", f"Couldn't read {doc.original_name}",
                               f"{doc.extraction_error or 'No text found.'} A reviewer needs to check this document manually.",
                               document=doc))
    return out


# --------------------------------------------------------------------- mismatch

def check_mismatches(claim, documents):
    out = []
    readable = [d for d in documents if d.extraction_status == "done"]
    primary = [d for d in readable if d.doc_type in PRIMARY_TYPES]
    payments = [d for d in readable if d.doc_type == "payment_proof"]
    claimed = float(claim.amount)

    def close(a, b):
        return abs(a - b) <= max(1.0, 0.01 * max(a, b))

    # Amount: one invoice matches, or invoices add up to the claim
    primary_amounts = [(d, float(d.extracted_data["amount"])) for d in primary if d.extracted_data.get("amount")]
    if primary_amounts:
        total = sum(a for _, a in primary_amounts)
        if not any(close(a, claimed) for _, a in primary_amounts) and not close(total, claimed):
            diff = claimed - total
            out.append(finding(
                "MISMATCH", "high" if abs(diff) > 0.05 * claimed else "medium",
                "Claimed amount doesn't match the documents",
                f"You claimed {money(claimed)} but the uploaded bills total {money(total)} "
                f"({'over' if diff > 0 else 'under'} by {money(abs(diff))}).",
                [_ev("Claim form", money(claimed), "Entered by employee")]
                + [_ev(d.get_doc_type_display(), money(a), d.original_name) for d, a in primary_amounts],
                document=primary_amounts[0][0],
            ))
    for doc in payments:
        paid = doc.extracted_data.get("amount")
        if paid and not any(close(float(paid), a) for _, a in primary_amounts) and not close(float(paid), claimed):
            out.append(finding("MISMATCH", "medium", "Payment proof amount differs",
                               f"The payment proof shows {money(paid)}, which doesn't match the claim or any bill.",
                               [_ev("Payment proof", money(paid), doc.original_name), _ev("Claim form", money(claimed))],
                               document=doc))

    # Invoice number
    if claim.invoice_number:
        doc_refs = [(d, d.extracted_data.get("invoice_number")) for d in primary if d.extracted_data.get("invoice_number")]
        if doc_refs and not any(norm_ref(r) == norm_ref(claim.invoice_number) for _, r in doc_refs):
            out.append(finding("MISMATCH", "medium", "Invoice number doesn't match",
                               "The invoice number entered on the form isn't on any uploaded bill.",
                               [_ev("Claim form", claim.invoice_number)] + [_ev(d.get_doc_type_display(), r, d.original_name) for d, r in doc_refs],
                               document=doc_refs[0][0]))

    # Dates
    start = claim.start_date or claim.expense_date
    end = claim.end_date or claim.expense_date
    for doc in readable:
        doc_date = parse_iso(doc.extracted_data.get("date"))
        if not doc_date or not start:
            continue
        late_slack = 3 if doc.doc_type == "payment_proof" else 1
        early_slack = 60 if doc.doc_type in ("ticket", "approval", "payment_proof") and claim.category == "travel" else late_slack
        if (doc_date - end).days > late_slack or (start - doc_date).days > early_slack:
            out.append(finding("MISMATCH", "medium", f"{doc.get_doc_type_display()} date is outside the claim period",
                               f"The document is dated {doc_date:%d %b %Y}, but the claim covers {start:%d %b %Y} to {end:%d %b %Y}.",
                               [_ev("Document date", f"{doc_date:%d %b %Y}", doc.original_name), _ev("Claim period", f"{start:%d %b %Y} – {end:%d %b %Y}")],
                               document=doc))
        check_in, check_out = parse_iso(doc.extracted_data.get("check_in")), parse_iso(doc.extracted_data.get("check_out"))
        if check_in and claim.start_date and check_in != claim.start_date:
            out.append(finding("MISMATCH", "medium", "Check-in date differs from the trip start",
                               f"The hotel bill shows check-in on {check_in:%d %b %Y}; the claim says {claim.start_date:%d %b %Y}.",
                               [_ev("Bill check-in", check_in, doc.original_name), _ev("Claim start", claim.start_date)], document=doc))
        if check_out and claim.end_date and check_out != claim.end_date:
            out.append(finding("MISMATCH", "medium", "Check-out date differs from the trip end",
                               f"The hotel bill shows check-out on {check_out:%d %b %Y}; the claim says {claim.end_date:%d %b %Y}.",
                               [_ev("Bill check-out", check_out, doc.original_name), _ev("Claim end", claim.end_date)], document=doc))

    # Employee name
    full_name = claim.employee.full_name
    for doc in readable:
        name = doc.extracted_data.get("employee_name")
        if name and fuzz.token_set_ratio(name.lower(), full_name.lower()) < 70:
            out.append(finding("MISMATCH", "high", f"Name on {doc.get_doc_type_display().lower()} is a different person",
                               f"The document is in the name of {name}, not {full_name}.",
                               [_ev("Document", name, doc.original_name), _ev("Employee", full_name)], document=doc))

    # Vendor
    if claim.vendor:
        for doc in primary:
            vendor = doc.extracted_data.get("vendor")
            if vendor and fuzz.token_set_ratio(vendor.lower(), claim.vendor.lower()) < 60:
                out.append(finding("MISMATCH", "low", "Vendor name differs",
                                   f"The form says {claim.vendor}; the bill appears to be from {vendor}.",
                                   [_ev("Claim form", claim.vendor), _ev("Document", vendor, doc.original_name)], document=doc))
    return out


# ------------------------------------------------------------- policy checks

def check_policies(claim, documents, applicable, superseded):
    out = []
    grade, dept = claim.employee.grade, claim.employee.department
    if not [p for p in applicable if p.category != "all"]:
        out.append(finding("VIOLATION", "high", "No policy covers this expense",
                           f"No active {claim.get_category_display().lower()} policy applies to grade {grade}"
                           f"{' in ' + dept if dept else ''} on {claim.expense_date:%d %b %Y}. It may not be reimbursable.",
                           [_ev("Category", claim.get_category_display()), _ev("Grade", grade), _ev("Expense date", claim.expense_date)]))

    uploaded = {d.doc_type for d in documents}
    submitted_on = timezone.localdate(claim.submitted_at) if claim.submitted_at else timezone.localdate()
    amount = Decimal(claim.amount)

    for policy in applicable:
        # Limits
        if policy.limit_amount is not None:
            units, unit_label = 1, "claim"
            if policy.limit_basis == "per_day":
                units, unit_label = claim.period_days, "day"
            elif policy.limit_basis == "per_night":
                units, unit_label = claim.period_nights, "night"
            allowed = policy.limit_amount * units
            compared = amount
            if policy.limit_basis == "per_month":
                from claims.models import Claim

                month_total = (
                    Claim.objects.filter(employee=claim.employee, category=claim.category,
                                         expense_date__year=claim.expense_date.year, expense_date__month=claim.expense_date.month)
                    .exclude(pk=claim.pk).exclude(status__in=["DRAFT", "REJECTED"]).aggregate(s=Sum("amount"))["s"] or Decimal(0)
                )
                compared = amount + month_total
                unit_label = "month"
            if compared > allowed:
                excess = compared - allowed
                out.append(finding(
                    "VIOLATION", "high" if compared > allowed * Decimal("1.25") else "medium",
                    f"Over the {policy.code} limit by {money(excess)}",
                    f"{policy.title} allows {money(policy.limit_amount)} per {unit_label}"
                    f"{f' × {units} {unit_label}s' if units > 1 else ''} = {money(allowed)}. "
                    f"This claim{' plus earlier claims this month' if policy.limit_basis == 'per_month' else ''} comes to {money(compared)}.",
                    [_ev("Claimed", money(compared)), _ev("Allowed", money(allowed)), _ev("Excess", money(excess)),
                     _ev("Policy", f"{policy.code} v{policy.version} ({policy.get_source_display()})")],
                    policy=policy, policy_excerpt=excerpt(policy, "limit maximum amount allowed per"),
                ))
        # Submission window
        if policy.submission_window_days and claim.expense_date:
            late = (submitted_on - (claim.end_date or claim.expense_date)).days
            if late > policy.submission_window_days:
                out.append(finding("VIOLATION", "medium", "Submitted after the deadline",
                                   f"Claims must be submitted within {policy.submission_window_days} days of the expense. This one was submitted {late} days later.",
                                   [_ev("Expense ended", claim.end_date or claim.expense_date), _ev("Submitted", submitted_on), _ev("Window", f"{policy.submission_window_days} days")],
                                   policy=policy, policy_excerpt=excerpt(policy, "submitted within days deadline")))
        # Pre-approval
        if policy.preapproval_above is not None and amount > policy.preapproval_above and "approval" not in uploaded:
            out.append(finding("MISSING_DOCUMENT", "high", "Pre-approval document missing",
                               f"{policy.title} needs written pre-approval for amounts above {money(policy.preapproval_above)}. No approval document was uploaded.",
                               [_ev("Claimed", money(amount)), _ev("Pre-approval above", money(policy.preapproval_above))],
                               policy=policy, policy_excerpt=excerpt(policy, "prior approval pre-approval required above")))
    # Required documents: one finding listing everything missing and which policy asks for it
    missing = {}
    for policy in applicable:
        for req in policy.required_documents:
            if not (DOC_EQUIVALENTS.get(req, {req}) & uploaded):
                missing.setdefault(req, []).append(policy)
    if missing:
        labels = ", ".join(DOCUMENT_LABELS.get(m, m) for m in missing)
        first_policy = next(iter(missing.values()))[0]
        out.append(finding(
            "MISSING_DOCUMENT", "high" if len(missing) > 1 or any(m in PRIMARY_TYPES for m in missing) else "medium",
            f"Missing: {labels}",
            " ".join(
                f"{DOCUMENT_LABELS.get(doc, doc)} is required by " + " and ".join(f"{p.code} v{p.version}" for p in pols) + "."
                for doc, pols in missing.items()
            ),
            [_ev("Missing", labels), _ev("Uploaded", ", ".join(DOCUMENT_LABELS.get(u, u) for u in sorted(uploaded)) or "nothing")],
            policy=first_policy, policy_excerpt=excerpt(first_policy, "documents required supporting must attach"),
        ))

    # Conflicts between applicable policies
    by_id = {p.id: p for p in applicable}
    for conflict in detect_conflicts(applicable):
        involved = [by_id[i] for i in conflict["policies"] if i in by_id]
        out.append(finding("CONFLICT", "medium", "Policies disagree — needs clarification",
                           conflict["message"] + ". A reviewer must decide which rule applies.",
                           [_ev(f"{p.code} v{p.version}", p.get_source_display(), p.title) for p in involved],
                           policy=involved[0] if involved else None,
                           policy_excerpt="\n\n".join(excerpt(p, "limit allowed") for p in involved[:2])))

    # Version changed between expense and submission: reviewers should know which version was used
    for current in applicable:
        newer = [o for o in superseded if o.code == current.code and o.version > current.version
                 and o.effective_from <= submitted_on]
        if newer:
            nv = max(newer, key=lambda o: o.version)
            out.append(finding("OUTDATED_POLICY", "low", f"{current.code} changed after the expense",
                               f"The expense on {claim.expense_date:%d %b %Y} falls under v{current.version}. "
                               f"v{nv.version} took effect on {nv.effective_from:%d %b %Y} and was not applied.",
                               [_ev("Applied", f"v{current.version}"), _ev("Newer version", f"v{nv.version} from {nv.effective_from:%d %b %Y}")],
                               policy=current))
    return out


# -------------------------------------------------------------------- duplicates

def check_duplicates(claim, documents):
    from claims.models import Claim, ClaimDocument

    out, seen = [], set()
    others = Claim.objects.exclude(pk=claim.pk).exclude(status="DRAFT")
    other_docs = list(ClaimDocument.objects.filter(claim__in=others).select_related("claim", "claim__employee"))

    def add(other, severity, title, explanation, evidence, doc=None):
        key = (other.pk, title)
        if key in seen:
            return
        seen.add(key)
        same_person = other.employee_id == claim.employee_id
        out.append(finding("DUPLICATE", severity, title,
                           explanation + (" Same employee." if same_person else f" Filed by {other.employee.full_name}."),
                           evidence + [_ev("Other claim", f"{other.claim_number} · {other.get_status_display()}")],
                           related_claim=other, document=doc))

    my_refs = {norm_ref(claim.invoice_number)} if claim.invoice_number else set()
    my_refs |= {norm_ref(d.extracted_data.get("invoice_number")) for d in documents if d.extracted_data.get("invoice_number")}
    my_refs.discard("")
    if my_refs:
        for other in others.filter(invoice_number__isnull=False).exclude(invoice_number=""):
            if norm_ref(other.invoice_number) in my_refs:
                add(other, "high", "Invoice number already claimed",
                    f"Invoice {other.invoice_number} was already used in {other.claim_number}.", [_ev("Invoice", other.invoice_number)])
        for od in other_docs:
            ref = norm_ref(od.extracted_data.get("invoice_number"))
            if ref and ref in my_refs:
                add(od.claim, "high", "Invoice number already claimed",
                    f"A bill with number {od.extracted_data.get('invoice_number')} is attached to {od.claim.claim_number}.",
                    [_ev("Invoice", od.extracted_data.get("invoice_number"))])

    for doc in documents:
        for od in other_docs:
            if doc.file_hash and doc.file_hash == od.file_hash:
                add(od.claim, "high", "Same file uploaded before",
                    f"{doc.original_name} is byte-for-byte identical to a file in {od.claim.claim_number}.",
                    [_ev("File", doc.original_name)], doc)
            elif doc.image_hash and od.image_hash and len(doc.image_hash) == len(od.image_hash):
                distance = sum(bin(int(a, 16) ^ int(b, 16)).count("1") for a, b in zip(doc.image_hash, od.image_hash))
                a1, a2 = doc.extracted_data.get("amount"), od.extracted_data.get("amount")
                if distance <= 3 and (a1 is None or a2 is None or float(a1) == float(a2)):
                    add(od.claim, "high", "Document looks visually identical",
                        f"{doc.original_name} looks like the same image as a document in {od.claim.claim_number} (perceptual hash distance {distance}).",
                        [_ev("Similarity", f"{100 - distance * 3}%")], doc)
            elif len(doc.extracted_text) > 120 and len(od.extracted_text) > 120:
                score = fuzz.ratio(doc.extracted_text[:3000], od.extracted_text[:3000])
                if score >= 92:
                    add(od.claim, "medium", "Document text is nearly identical",
                        f"The text of {doc.original_name} is {score:.0f}% similar to a document in {od.claim.claim_number}.",
                        [_ev("Text similarity", f"{score:.0f}%")], doc)

    for other in others.filter(amount=claim.amount, expense_date=claim.expense_date):
        if not claim.vendor or not other.vendor or fuzz.token_set_ratio(claim.vendor.lower(), other.vendor.lower()) >= 85:
            add(other, "high" if other.employee_id == claim.employee_id else "medium",
                "Same amount, date and vendor as another claim",
                f"{other.claim_number} has the same amount ({money(other.amount)}) on {other.expense_date:%d %b %Y}"
                f"{' from ' + other.vendor if other.vendor else ''}.",
                [_ev("Amount", money(other.amount)), _ev("Date", other.expense_date)])
    return out
