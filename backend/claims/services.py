"""Claim workflow: submit, act on approval steps, settle payment. Every change is audited."""
from decimal import Decimal

from django.db import transaction
from django.utils import timezone
from rest_framework.exceptions import PermissionDenied, ValidationError

from accounts.models import User

from .models import ApprovalStep, Claim, ClaimEvent, Payment
from .verification.engine import verify_claim
from .verification.explain import RECOMMENDATION_LABELS
from .verification.routing import ROLE_LABELS, build_chain


def log(claim, actor, action, message, **data):
    return ClaimEvent.objects.create(claim=claim, actor=actor, action=action, message=message, data=data)


def can_act(user, step):
    if step is None or step.status != ApprovalStep.Status.PENDING:
        return False
    if step.claim.employee_id == user.id:
        return False
    if user.role == User.Role.ADMIN:
        return True
    if step.approver_id:
        return step.approver_id == user.id
    return user.role == step.role


@transaction.atomic
def submit(claim, user):
    if claim.employee_id != user.id:
        raise PermissionDenied("Only the employee who owns this claim can submit it.")
    if not claim.is_editable:
        raise ValidationError("This claim has already been submitted.")
    if not claim.documents.exists():
        raise ValidationError("Upload at least one supporting document before submitting.")
    resubmission = claim.status != Claim.Status.DRAFT
    claim.submitted_at = timezone.now()
    claim.review_round += 1
    claim.status = Claim.Status.UNDER_REVIEW
    claim.approved_amount = None
    claim.save()
    log(claim, user, "RESUBMITTED" if resubmission else "SUBMITTED",
        "Claim resubmitted after changes" if resubmission else "Claim submitted for verification")

    findings = verify_claim(claim)
    log(claim, None, "VERIFIED",
        f"Automatic verification finished: {len(findings)} finding(s), risk {claim.risk_score}/100. "
        f"Recommendation: {RECOMMENDATION_LABELS.get(claim.ai_recommendation, '')}.",
        risk=claim.risk_score, findings=len(findings))

    steps = build_chain(claim, findings)
    claim.save(update_fields=["verification_level"])
    log(claim, None, "ROUTED", f"Routed for approval. {claim.verification_level}.",
        chain=[s.role for s in steps])
    return claim


@transaction.atomic
def reverify(claim, user):
    findings = verify_claim(claim)
    log(claim, user, "REVERIFIED", f"Verification re-run by {user.full_name}: {len(findings)} finding(s), risk {claim.risk_score}/100.")
    return claim


@transaction.atomic
def act(claim, user, action, comment="", approved_amount=None):
    step = claim.current_step()
    if not can_act(user, step):
        raise PermissionDenied("This claim isn't waiting for your decision.")
    comment = (comment or "").strip()
    now = timezone.now()
    step.acted_by, step.acted_at, step.comment = user, now, comment
    role_label = ROLE_LABELS.get(step.role, step.role)

    if action == "approve":
        if approved_amount not in (None, ""):
            value = Decimal(str(approved_amount))
            if value <= 0 or value > claim.amount:
                raise ValidationError("Approved amount must be more than zero and not more than the claimed amount.")
            claim.approved_amount = value
        step.status = ApprovalStep.Status.APPROVED
        step.save()
        amount_note = f" Approved amount set to ₹{claim.approved_amount:,.2f}." if approved_amount not in (None, "") else ""
        log(claim, user, "APPROVED_STEP", f"{role_label} approval given by {user.full_name}.{amount_note}" + (f" Comment: {comment}" if comment else ""))
        nxt = claim.steps.filter(round=claim.review_round, status=ApprovalStep.Status.WAITING).order_by("sequence").first()
        if nxt:
            nxt.status, nxt.activated_at = ApprovalStep.Status.PENDING, now
            nxt.save()
            log(claim, None, "FORWARDED", f"Forwarded to {ROLE_LABELS.get(nxt.role, nxt.role)}"
                + (f" ({nxt.approver.full_name})" if nxt.approver else "") + ".")
        else:
            claim.status = Claim.Status.APPROVED
            claim.decided_at = now
            if claim.approved_amount is None:
                claim.approved_amount = claim.amount
            claim.save()
            Payment.objects.update_or_create(
                claim=claim,
                defaults={"approved_amount": claim.approved_amount, "status": Payment.Status.PENDING, "due_date": Payment.due_from(now),
                          "deductions": Decimal(0)},
            )
            log(claim, None, "APPROVED", f"Claim fully approved for ₹{claim.approved_amount:,.2f}. Payment due by {Payment.due_from(now):%d %b %Y}.")
        claim.save()
        return claim

    if not comment:
        raise ValidationError("Add a comment so the employee knows what to do.")

    remaining = claim.steps.filter(round=claim.review_round, status=ApprovalStep.Status.WAITING)
    if action == "reject":
        step.status = ApprovalStep.Status.REJECTED
        claim.status = Claim.Status.REJECTED
        claim.decided_at = now
        message = f"Rejected by {user.full_name} ({role_label}): {comment}"
        event = "REJECTED"
    elif action == "request_correction":
        step.status = ApprovalStep.Status.CORRECTION_REQUESTED
        claim.status = Claim.Status.CORRECTION_REQUESTED
        message = f"{user.full_name} ({role_label}) asked for corrections: {comment}"
        event = "CORRECTION_REQUESTED"
    elif action == "request_documents":
        step.status = ApprovalStep.Status.DOCS_REQUESTED
        claim.status = Claim.Status.DOCS_REQUESTED
        message = f"{user.full_name} ({role_label}) asked for more documents: {comment}"
        event = "DOCS_REQUESTED"
    else:
        raise ValidationError("Unknown action.")
    step.save()
    remaining.update(status=ApprovalStep.Status.SKIPPED)
    claim.save()
    log(claim, user, event, message)
    return claim


@transaction.atomic
def initiate_payment(claim, user, method, deductions=0, deduction_reason="", remarks=""):
    if user.role not in (User.Role.FINANCE, User.Role.ADMIN):
        raise PermissionDenied("Only Finance can initiate payments.")
    if claim.status != Claim.Status.APPROVED:
        raise ValidationError("Only approved claims can be paid.")
    payment = claim.payment
    deductions = Decimal(str(deductions or 0))
    if deductions < 0 or deductions >= payment.approved_amount:
        raise ValidationError("Deductions must be zero or more and less than the approved amount.")
    if deductions and not deduction_reason:
        raise ValidationError("Give a reason for the deduction.")
    payment.method, payment.deductions, payment.deduction_reason, payment.remarks = method, deductions, deduction_reason, remarks
    payment.status, payment.initiated_at, payment.initiated_by = Payment.Status.INITIATED, timezone.now(), user
    payment.save()
    claim.status = Claim.Status.PAYMENT_INITIATED
    claim.save()
    log(claim, user, "PAYMENT_INITIATED",
        f"Payment of ₹{payment.net_amount:,.2f} initiated via {payment.get_method_display()}"
        + (f" after deducting ₹{deductions:,.2f} ({deduction_reason})" if deductions else "") + ".")
    return claim


@transaction.atomic
def complete_payment(claim, user, reference_number, paid_on=None):
    if user.role not in (User.Role.FINANCE, User.Role.ADMIN):
        raise PermissionDenied("Only Finance can record payments.")
    if claim.status != Claim.Status.PAYMENT_INITIATED:
        raise ValidationError("Initiate the payment first.")
    if not (reference_number or "").strip():
        raise ValidationError("Enter the bank or UPI reference number.")
    payment = claim.payment
    payment.reference_number = reference_number.strip()
    payment.paid_at = paid_on or timezone.now()
    payment.status = Payment.Status.PAID
    payment.save()
    claim.status = Claim.Status.PAID
    claim.save()
    late = f" Paid {payment.days_overdue} day(s) after the due date." if payment.is_delayed else ""
    log(claim, user, "PAID", f"Settled: ₹{payment.net_amount:,.2f} paid, reference {payment.reference_number}.{late}")
    return claim
