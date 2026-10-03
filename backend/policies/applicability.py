"""Work out which policy versions apply to a claim, and where policies disagree."""
from collections import defaultdict
from decimal import Decimal

from django.db.models import Q

from .models import Policy


def candidate_policies(category):
    return Policy.objects.filter(is_active=True).filter(Q(category=category) | Q(category="all"))


def applicable_policies(category, grade, department, on_date):
    """Return (applicable, superseded).

    applicable: one policy per code — the latest version whose effective window covers on_date
    and whose grade/department filter includes the employee.
    superseded: other versions of the same codes that would have matched the person but not the date,
    or that were replaced by a newer version. Shown to reviewers so outdated rules are visible.
    """
    by_code = defaultdict(list)
    for policy in candidate_policies(category):
        if policy.covers_person(grade, department):
            by_code[policy.code].append(policy)

    applicable, superseded = [], []
    for code, versions in by_code.items():
        versions.sort(key=lambda p: (p.effective_from, p.version), reverse=True)
        in_force = [p for p in versions if p.covers_date(on_date)]
        if in_force:
            chosen = in_force[0]
            applicable.append(chosen)
            superseded.extend(p for p in versions if p.pk != chosen.pk)
        else:
            superseded.extend(versions)
    applicable.sort(key=lambda p: (p.category == "all", p.code))
    return applicable, superseded


def _fmt(amount):
    return f"₹{Decimal(amount):,.0f}"


def detect_conflicts(policies):
    """Find applicable policies that give different answers to the same question."""
    conflicts = []
    limited = [p for p in policies if p.limit_amount is not None and p.category != "all"]
    by_basis = defaultdict(list)
    for p in limited:
        by_basis[p.limit_basis].append(p)
    for basis, group in by_basis.items():
        amounts = {p.limit_amount for p in group}
        if len(amounts) > 1:
            conflicts.append(
                {
                    "type": "limit",
                    "basis": basis,
                    "policies": [p.id for p in group],
                    "message": "Different limits for the same expense: "
                    + "; ".join(f"{p.code} v{p.version} ({p.get_source_display()}) allows {_fmt(p.limit_amount)} {p.get_limit_basis_display().lower()}" for p in group),
                }
            )

    windows = {p.submission_window_days for p in policies if p.submission_window_days}
    if len(windows) > 1:
        group = [p for p in policies if p.submission_window_days]
        conflicts.append(
            {
                "type": "submission_window",
                "policies": [p.id for p in group],
                "message": "Different submission deadlines: "
                + "; ".join(f"{p.code} v{p.version} says {p.submission_window_days} days" for p in group),
            }
        )

    thresholds = {p.preapproval_above for p in policies if p.preapproval_above is not None}
    if len(thresholds) > 1:
        group = [p for p in policies if p.preapproval_above is not None]
        conflicts.append(
            {
                "type": "preapproval",
                "policies": [p.id for p in group],
                "message": "Different pre-approval thresholds: "
                + "; ".join(f"{p.code} v{p.version} above {_fmt(p.preapproval_above)}" for p in group),
            }
        )
    return conflicts


def knowledge_base_conflicts():
    """Scan the whole knowledge base for overlapping policies that disagree (admin view)."""
    results = []
    policies = list(Policy.objects.filter(is_active=True))
    categories = {p.category for p in policies if p.category != "all"}
    for category in sorted(categories):
        group = [p for p in policies if p.category == category]
        for i, a in enumerate(group):
            for b in group[i + 1:]:
                if a.code == b.code:
                    continue
                if not _overlap(a, b):
                    continue
                issues = []
                if a.limit_amount and b.limit_amount and a.limit_basis == b.limit_basis and a.limit_amount != b.limit_amount:
                    issues.append(f"limit {_fmt(a.limit_amount)} vs {_fmt(b.limit_amount)} {a.get_limit_basis_display().lower()}")
                if set(a.required_documents) != set(b.required_documents) and a.required_documents and b.required_documents:
                    issues.append("different required documents")
                if issues:
                    results.append(
                        {
                            "category": category,
                            "a": {"id": a.id, "label": f"{a.code} v{a.version}", "title": a.title, "source": a.get_source_display()},
                            "b": {"id": b.id, "label": f"{b.code} v{b.version}", "title": b.title, "source": b.get_source_display()},
                            "issues": issues,
                        }
                    )
    for p in policies:
        newer = [q for q in policies if q.code == p.code and q.version > p.version]
        if newer and (p.effective_to is None or any(n.effective_from <= (p.effective_to or n.effective_from) for n in newer)):
            results.append(
                {
                    "category": p.category,
                    "a": {"id": p.id, "label": f"{p.code} v{p.version}", "title": p.title, "source": p.get_source_display()},
                    "b": {"id": newer[0].id, "label": f"{newer[0].code} v{newer[0].version}", "title": newer[0].title, "source": newer[0].get_source_display()},
                    "issues": ["older version has no end date or overlaps the newer version"],
                }
            )
    return results


def _people_overlap(a, b):
    if a.applicable_grades and b.applicable_grades and not set(a.applicable_grades) & set(b.applicable_grades):
        return False
    if a.applicable_departments and b.applicable_departments and not set(a.applicable_departments) & set(b.applicable_departments):
        return False
    return True


def _overlap(a, b):
    if not _people_overlap(a, b):
        return False
    a_end = a.effective_to
    b_end = b.effective_to
    if a_end and a_end < b.effective_from:
        return False
    if b_end and b_end < a.effective_from:
        return False
    return True
