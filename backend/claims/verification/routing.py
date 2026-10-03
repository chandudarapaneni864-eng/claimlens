"""Dynamic verification level: decide who must approve this claim and why."""
from decimal import Decimal, InvalidOperation

from django.utils import timezone

from accounts.models import User

ROLE_ORDER = ["MANAGER", "DEPT_HEAD", "HR", "FINANCE"]
ROLE_LABELS = {"MANAGER": "Manager", "DEPT_HEAD": "Department head", "HR": "HR", "FINANCE": "Finance"}


def _rule_matches(rule, claim, kinds):
    value = (rule.value or "").strip()
    try:
        if rule.condition == "amount_gte":
            return Decimal(claim.amount) >= Decimal(value)
        if rule.condition == "risk_gte":
            return claim.risk_score >= int(value)
        if rule.condition == "category_is":
            return claim.category == value.lower()
        if rule.condition == "has_finding":
            return value.upper() in kinds
        if rule.condition == "grade_in":
            return claim.employee.grade in {g.strip().upper() for g in value.split(",")}
    except (InvalidOperation, ValueError):
        return False
    return False


def required_roles(claim, findings):
    from claims.models import RoutingRule

    kinds = {f["kind"] for f in findings}
    roles = {"MANAGER": ["Reporting manager reviews every claim"], "FINANCE": ["Finance verifies before payment"]}
    for rule in RoutingRule.objects.filter(is_active=True):
        if _rule_matches(rule, claim, kinds):
            roles.setdefault(rule.add_role, []).append(rule.name)
    return [(role, "; ".join(roles[role])[:255]) for role in ROLE_ORDER if role in roles]


def pick_approver(role, claim):
    employee = claim.employee
    base = User.objects.filter(is_active=True).exclude(pk=employee.pk)
    if role == "MANAGER":
        if employee.manager and employee.manager.is_active and employee.manager_id != employee.pk:
            return employee.manager
        return base.filter(role="MANAGER", department=employee.department).first() or base.filter(role="MANAGER").first()
    if role == "DEPT_HEAD":
        return base.filter(role="DEPT_HEAD", department=employee.department).first() or base.filter(role="DEPT_HEAD").first()
    return base.filter(role=role).first()


def level_label(roles):
    extra = len(roles) - 2
    level = 1 if extra <= 0 else (2 if extra == 1 else 3)
    chain = " → ".join(ROLE_LABELS[r] for r, _ in roles)
    return f"Level {level}: {chain}"


def build_chain(claim, findings):
    from claims.models import ApprovalStep

    roles = required_roles(claim, findings)
    claim.verification_level = level_label(roles)
    now = timezone.now()
    steps = []
    for seq, (role, reason) in enumerate(roles, start=1):
        steps.append(ApprovalStep.objects.create(
            claim=claim, round=claim.review_round, sequence=seq, role=role,
            approver=pick_approver(role, claim), reason=reason,
            status=ApprovalStep.Status.PENDING if seq == 1 else ApprovalStep.Status.WAITING,
            activated_at=now if seq == 1 else None,
        ))
    return steps
