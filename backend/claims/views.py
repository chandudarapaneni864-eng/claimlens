from collections import Counter, OrderedDict
from datetime import date

from django.db.models import Count, Prefetch, Q, Sum
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.models import User
from accounts.permissions import IsAdminRole, IsFinanceOrAdmin, IsOversight
from policies.models import CATEGORY_CHOICES

from . import services
from .models import ApprovalStep, Claim, ClaimDocument, Finding, Payment, RoutingRule
from .serializers import (
    ClaimDetailSerializer, ClaimListSerializer, DocumentSerializer, DocumentUploadSerializer,
    PaymentRowSerializer, RoutingRuleSerializer,
)
from .verification.extraction import extract_document
from .verification.routing import ROLE_LABELS

OVERSIGHT = {User.Role.FINANCE, User.Role.ADMIN, User.Role.HR}


def visible_claims(user):
    qs = Claim.objects.all()
    if user.role in OVERSIGHT:
        return qs
    cond = Q(employee=user) | Q(steps__approver=user) | Q(employee__manager=user)
    if user.role == User.Role.DEPT_HEAD and user.department:
        cond |= Q(employee__department=user.department)
    if user.role in (User.Role.MANAGER, User.Role.DEPT_HEAD):
        cond |= Q(steps__approver__isnull=True, steps__role=user.role)
    return qs.filter(cond).distinct()


def with_related(qs):
    return qs.select_related("employee", "employee__manager").prefetch_related(
        Prefetch("steps", queryset=ApprovalStep.objects.select_related("approver", "acted_by"))
    )


class ClaimViewSet(viewsets.ModelViewSet):
    def get_serializer_class(self):
        return ClaimListSerializer if self.action == "list" else ClaimDetailSerializer

    def get_queryset(self):
        user = self.request.user
        params = self.request.query_params
        if self.action == "list":
            scope = params.get("scope", "mine")
            if scope == "all" and user.role in OVERSIGHT:
                qs = Claim.objects.exclude(status=Claim.Status.DRAFT)
            elif scope == "team":
                cond = Q(employee__manager=user)
                if user.role == User.Role.DEPT_HEAD:
                    cond |= Q(employee__department=user.department)
                qs = Claim.objects.filter(cond).exclude(employee=user).exclude(status=Claim.Status.DRAFT)
            else:
                qs = Claim.objects.filter(employee=user)
            if params.get("status"):
                qs = qs.filter(status__in=params["status"].split(","))
            if params.get("category"):
                qs = qs.filter(category=params["category"])
            if params.get("risk"):
                qs = qs.filter(risk_level=params["risk"])
            if params.get("q"):
                q = params["q"]
                qs = qs.filter(Q(claim_number__icontains=q) | Q(title__icontains=q) | Q(vendor__icontains=q) |
                               Q(employee__first_name__icontains=q) | Q(employee__last_name__icontains=q))
            return with_related(qs.annotate(finding_count=Count("findings", distinct=True))).order_by("-created_at")
        return with_related(visible_claims(user)).prefetch_related(
            "documents", "events__actor", Prefetch("findings", queryset=Finding.objects.select_related("policy", "related_claim", "document"))
        )

    def perform_create(self, serializer):
        claim = serializer.save(employee=self.request.user, status=Claim.Status.DRAFT)
        services.log(claim, self.request.user, "CREATED", "Draft claim created")

    def perform_update(self, serializer):
        claim = self.get_object()
        if claim.employee_id != self.request.user.id or not claim.is_editable:
            raise PermissionDenied("This claim can't be edited now.")
        changed = [k for k, v in serializer.validated_data.items() if getattr(claim, k) != v]
        claim = serializer.save()
        if changed:
            services.log(claim, self.request.user, "EDITED", "Updated " + ", ".join(f.replace("_", " ") for f in changed))

    def perform_destroy(self, instance):
        if instance.employee_id != self.request.user.id or instance.status != Claim.Status.DRAFT:
            raise PermissionDenied("Only your own drafts can be deleted.")
        instance.delete()

    def _detail(self, claim):
        claim = self.get_queryset().get(pk=claim.pk)
        return Response(ClaimDetailSerializer(claim, context={"request": self.request}).data)

    @action(detail=True, methods=["post"])
    def documents(self, request, pk=None):
        claim = self.get_object()
        if claim.employee_id != request.user.id or not claim.is_editable:
            raise PermissionDenied("Documents can only be added while the claim is a draft or sent back to you.")
        ser = DocumentUploadSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        upload = ser.validated_data["file"]
        doc = ClaimDocument.objects.create(
            claim=claim, doc_type=ser.validated_data["doc_type"], file=upload, original_name=upload.name[:255],
            size=upload.size, uploaded_by=request.user,
        )
        extract_document(doc)
        services.log(claim, request.user, "DOCUMENT_UPLOADED", f"Uploaded {doc.get_doc_type_display().lower()}: {doc.original_name}")
        return Response(DocumentSerializer(doc, context={"request": request}).data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=["post"])
    def submit(self, request, pk=None):
        claim = services.submit(self.get_object(), request.user)
        return self._detail(claim)

    @action(detail=True, methods=["post"])
    def decide(self, request, pk=None):
        claim = services.act(
            self.get_object(), request.user, request.data.get("action"),
            request.data.get("comment", ""), request.data.get("approved_amount"),
        )
        return self._detail(claim)

    @action(detail=True, methods=["post"])
    def reverify(self, request, pk=None):
        if request.user.role not in OVERSIGHT:
            raise PermissionDenied()
        return self._detail(services.reverify(self.get_object(), request.user))

    @action(detail=True, methods=["post"], url_path="payment/initiate")
    def initiate_payment(self, request, pk=None):
        claim = services.initiate_payment(
            self.get_object(), request.user, request.data.get("method", "bank_transfer"),
            request.data.get("deductions") or 0, request.data.get("deduction_reason", ""), request.data.get("remarks", ""),
        )
        return self._detail(claim)

    @action(detail=True, methods=["post"], url_path="payment/complete")
    def complete_payment(self, request, pk=None):
        paid_on = None
        if request.data.get("paid_on"):
            try:
                d = date.fromisoformat(request.data["paid_on"])
                paid_on = timezone.make_aware(timezone.datetime(d.year, d.month, d.day, 12, 0))
            except ValueError:
                raise ValidationError("Paid date must be YYYY-MM-DD.")
        claim = services.complete_payment(self.get_object(), request.user, request.data.get("reference_number", ""), paid_on)
        return self._detail(claim)


class DocumentViewSet(mixins.DestroyModelMixin, viewsets.GenericViewSet):
    queryset = ClaimDocument.objects.select_related("claim")

    def perform_destroy(self, doc):
        claim = doc.claim
        if claim.employee_id != self.request.user.id or not claim.is_editable:
            raise PermissionDenied("This document can't be removed now.")
        services.log(claim, self.request.user, "DOCUMENT_REMOVED", f"Removed {doc.original_name}")
        doc.file.delete(save=False)
        doc.delete()


class ApprovalQueueView(APIView):
    def get(self, request):
        user = request.user
        if request.query_params.get("view") == "history":
            steps = (ApprovalStep.objects.filter(acted_by=user).select_related("claim", "claim__employee")
                     .order_by("-acted_at")[:100])
        else:
            steps = ApprovalStep.objects.filter(status=ApprovalStep.Status.PENDING, claim__status=Claim.Status.UNDER_REVIEW)
            if user.role != User.Role.ADMIN:
                steps = steps.filter(Q(approver=user) | Q(approver__isnull=True, role=user.role))
            steps = steps.exclude(claim__employee=user).select_related("claim", "claim__employee").order_by("activated_at")
        today = timezone.now()
        rows = []
        for s in steps:
            c = s.claim
            if s.round != c.review_round and s.status == ApprovalStep.Status.PENDING:
                continue
            rows.append({
                "step_id": s.id, "role": s.role, "role_label": ROLE_LABELS.get(s.role, s.role), "status": s.status,
                "status_label": s.get_status_display(), "reason": s.reason, "acted_at": s.acted_at, "comment": s.comment,
                "waiting_days": (today - s.activated_at).days if s.activated_at and s.status == "PENDING" else None,
                "claim": {
                    "id": c.id, "claim_number": c.claim_number, "title": c.title, "amount": str(c.amount),
                    "category": c.category, "category_label": c.get_category_display(), "employee_name": c.employee.full_name,
                    "department": c.employee.department, "risk_score": c.risk_score, "risk_level": c.risk_level,
                    "ai_recommendation": c.ai_recommendation, "finding_count": c.findings.count(),
                    "submitted_at": c.submitted_at, "status_label": c.get_status_display(),
                },
            })
        return Response(rows)


class PaymentListView(APIView):
    permission_classes = [IsFinanceOrAdmin]

    def get(self, request):
        qs = Payment.objects.select_related("claim", "claim__employee", "initiated_by").order_by("due_date")
        st = request.query_params.get("status")
        if st:
            qs = qs.filter(status=st)
        rows = PaymentRowSerializer(qs, many=True).data
        if request.query_params.get("delayed") == "1":
            rows = [r for r in rows if r["is_delayed"]]
        return Response(rows)


class DashboardView(APIView):
    """Personal summary for whoever is logged in."""

    def get(self, request):
        user = request.user
        mine = Claim.objects.filter(employee=user)
        by_status = Counter(mine.values_list("status", flat=True))
        settled = Payment.objects.filter(claim__employee=user, status=Payment.Status.PAID)
        pending_steps = ApprovalStep.objects.filter(status=ApprovalStep.Status.PENDING, claim__status=Claim.Status.UNDER_REVIEW)
        if user.role != User.Role.ADMIN:
            pending_steps = pending_steps.filter(Q(approver=user) | Q(approver__isnull=True, role=user.role))
        pending_steps = pending_steps.exclude(claim__employee=user)
        recent = with_related(mine.annotate(finding_count=Count("findings", distinct=True))).order_by("-updated_at")[:6]
        action_needed = mine.filter(status__in=[Claim.Status.CORRECTION_REQUESTED, Claim.Status.DOCS_REQUESTED])
        return Response({
            "counts": {
                "total": mine.exclude(status=Claim.Status.DRAFT).count(),
                "drafts": by_status.get("DRAFT", 0),
                "in_review": by_status.get("UNDER_REVIEW", 0),
                "action_needed": action_needed.count(),
                "approved": by_status.get("APPROVED", 0) + by_status.get("PAYMENT_INITIATED", 0),
                "settled": by_status.get("PAID", 0),
                "rejected": by_status.get("REJECTED", 0),
            },
            "amounts": {
                "claimed": mine.exclude(status__in=["DRAFT"]).aggregate(s=Sum("amount"))["s"] or 0,
                "settled": sum((p.net_amount for p in settled), 0),
                "awaiting_payment": mine.filter(status__in=["APPROVED", "PAYMENT_INITIATED"]).aggregate(s=Sum("approved_amount"))["s"] or 0,
            },
            "approvals_waiting": pending_steps.count(),
            "action_needed": ClaimListSerializer(with_related(action_needed.annotate(finding_count=Count("findings", distinct=True))), many=True).data,
            "recent": ClaimListSerializer(recent, many=True).data,
        })


class AnalyticsView(APIView):
    permission_classes = [IsOversight]

    def get(self, request):
        claims = Claim.objects.exclude(status=Claim.Status.DRAFT).select_related("employee")
        claim_list = list(claims)
        status_labels = dict(Claim.Status.choices)
        cat_labels = dict(CATEGORY_CHOICES)

        status_counts = Counter(c.status for c in claim_list)
        by_category = OrderedDict((k, {"key": k, "label": v, "count": 0, "amount": 0.0}) for k, v in CATEGORY_CHOICES)
        for c in claim_list:
            by_category[c.category]["count"] += 1
            by_category[c.category]["amount"] += float(c.amount)

        today = timezone.localdate()
        months = []
        y, m = today.year, today.month
        for _ in range(6):
            months.append((y, m))
            m -= 1
            if m == 0:
                y, m = y - 1, 12
        months.reverse()
        monthly = OrderedDict(((yy, mm), {"label": date(yy, mm, 1).strftime("%b %Y"), "count": 0, "amount": 0.0, "approved": 0, "rejected": 0}) for yy, mm in months)
        for c in claim_list:
            if not c.submitted_at:
                continue
            d = timezone.localtime(c.submitted_at)
            key = (d.year, d.month)
            if key in monthly:
                monthly[key]["count"] += 1
                monthly[key]["amount"] += float(c.amount)
                if c.status in ("APPROVED", "PAYMENT_INITIATED", "PAID"):
                    monthly[key]["approved"] += 1
                elif c.status == "REJECTED":
                    monthly[key]["rejected"] += 1

        finding_rows = Finding.objects.filter(claim__in=claims).values("kind").annotate(claims=Count("claim", distinct=True), total=Count("id"))
        kind_labels = dict(Finding.Kind.choices)
        findings = sorted(
            [{"kind": r["kind"], "label": kind_labels.get(r["kind"], r["kind"]), "claims": r["claims"], "total": r["total"]} for r in finding_rows],
            key=lambda r: -r["claims"],
        )
        finding_claims = {r["kind"]: r["claims"] for r in findings}

        decided = [c for c in claim_list if c.decided_at and c.submitted_at]
        avg_decision_hours = (sum((c.decided_at - c.submitted_at).total_seconds() for c in decided) / len(decided) / 3600) if decided else 0

        payments = list(Payment.objects.select_related("claim", "claim__employee"))
        paid = [p for p in payments if p.status == "PAID"]
        settle_days = [(p.paid_at - p.claim.submitted_at).total_seconds() / 86400 for p in paid if p.paid_at and p.claim.submitted_at]
        delayed_open = [p for p in payments if p.status != "PAID" and p.is_delayed]
        paid_late = [p for p in paid if p.is_delayed]

        pending = ApprovalStep.objects.filter(status="PENDING", claim__status="UNDER_REVIEW")
        workload = [{"role": r["role"], "label": ROLE_LABELS.get(r["role"], r["role"]), "count": r["n"]} for r in pending.values("role").annotate(n=Count("id")).order_by("role")]

        flagged = sorted([c for c in claim_list if c.status == "UNDER_REVIEW"], key=lambda c: -c.risk_score)[:6]
        risk = Counter(c.risk_level for c in claim_list)
        approved_n = sum(status_counts.get(s, 0) for s in ("APPROVED", "PAYMENT_INITIATED", "PAID"))
        decided_n = approved_n + status_counts.get("REJECTED", 0)

        return Response({
            "totals": {
                "claims": len(claim_list),
                "claimed_amount": sum(float(c.amount) for c in claim_list),
                "approved": approved_n,
                "rejected": status_counts.get("REJECTED", 0),
                "pending_verification": status_counts.get("UNDER_REVIEW", 0),
                "with_employee": status_counts.get("CORRECTION_REQUESTED", 0) + status_counts.get("DOCS_REQUESTED", 0),
                "approval_rate": round(100 * approved_n / decided_n, 1) if decided_n else 0,
                "reimbursed_amount": sum(float(p.net_amount) for p in paid),
                "awaiting_payment_amount": sum(float(p.net_amount) for p in payments if p.status != "PAID"),
                "missing_documents": finding_claims.get("MISSING_DOCUMENT", 0),
                "policy_violations": finding_claims.get("VIOLATION", 0),
                "duplicates": finding_claims.get("DUPLICATE", 0),
                "conflicts": finding_claims.get("CONFLICT", 0),
                "avg_decision_hours": round(avg_decision_hours, 1),
                "avg_settlement_days": round(sum(settle_days) / len(settle_days), 1) if settle_days else 0,
                "delayed_payments": len(delayed_open),
                "paid_late": len(paid_late),
            },
            "by_status": [{"key": k, "label": status_labels[k], "count": status_counts.get(k, 0)} for k in status_labels if k != "DRAFT"],
            "by_category": list(by_category.values()),
            "monthly": list(monthly.values()),
            "findings": findings,
            "risk": {"low": risk.get("low", 0), "medium": risk.get("medium", 0), "high": risk.get("high", 0)},
            "workload": workload,
            "flagged": [{"id": c.id, "claim_number": c.claim_number, "title": c.title, "employee_name": c.employee.full_name,
                         "amount": str(c.amount), "risk_score": c.risk_score, "risk_level": c.risk_level} for c in flagged],
            "delayed": [{"claim_id": p.claim_id, "claim_number": p.claim.claim_number, "employee_name": p.claim.employee.full_name,
                         "amount": str(p.net_amount), "due_date": p.due_date, "days_overdue": p.days_overdue, "status": p.get_status_display()}
                        for p in sorted(delayed_open, key=lambda p: -p.days_overdue)[:8]],
        })


class RoutingRuleViewSet(viewsets.ModelViewSet):
    queryset = RoutingRule.objects.all()
    serializer_class = RoutingRuleSerializer

    def get_permissions(self):
        if self.action in ("list", "retrieve"):
            return super().get_permissions()
        return [IsAdminRole()]
