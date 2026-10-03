"""Orchestrates a full verification run for one claim."""
from django.db import transaction
from django.utils import timezone

from policies import rag
from policies.applicability import applicable_policies

from . import checks, explain
from .extraction import extract_document


def _policy_dict(p):
    return {
        "id": p.id, "code": p.code, "version": p.version, "title": p.title, "source": p.get_source_display(),
        "category": p.category, "limit_amount": str(p.limit_amount) if p.limit_amount is not None else None,
        "limit_basis": p.get_limit_basis_display(), "required_documents": p.required_documents,
        "effective_from": p.effective_from.isoformat(), "effective_to": p.effective_to.isoformat() if p.effective_to else None,
    }


@transaction.atomic
def verify_claim(claim):
    from claims.models import Finding

    documents = list(claim.documents.all())
    for doc in documents:
        if doc.extraction_status == "pending":
            extract_document(doc)

    applicable, superseded = applicable_policies(
        claim.category, claim.employee.grade, claim.employee.department, claim.expense_date
    )
    retrieved = rag.search(rag.claim_query(claim), policy_ids=[p.id for p in applicable] or None, top_k=5)

    findings = []
    findings += checks.check_claim_basics(claim, documents)
    findings += checks.check_mismatches(claim, documents)
    findings += checks.check_policies(claim, documents, applicable, superseded)
    findings += checks.check_duplicates(claim, documents)

    claim.findings.all().delete()
    Finding.objects.bulk_create([
        Finding(claim=claim, kind=f["kind"], severity=f["severity"], title=f["title"][:200], explanation=f["explanation"],
                evidence=f["evidence"], policy=f["policy"], policy_excerpt=f["policy_excerpt"],
                related_claim=f["related_claim"], document=f["document"])
        for f in findings
    ])

    claim.risk_score, claim.risk_level = explain.risk(findings)
    claim.ai_recommendation = explain.recommendation(findings)
    claim.verification_summary = explain.summarise(claim, findings, applicable, retrieved)
    claim.policy_snapshot = {
        "applicable": [_policy_dict(p) for p in applicable],
        "superseded": [_policy_dict(p) for p in superseded],
        "retrieved": retrieved,
        "checked_on": timezone.now().isoformat(),
    }
    claim.verified_at = timezone.now()
    claim.save()
    return findings
