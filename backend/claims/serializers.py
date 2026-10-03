from pathlib import Path

from django.conf import settings
from django.utils import timezone
from rest_framework import serializers

from .models import ApprovalStep, Claim, ClaimDocument, ClaimEvent, Finding, Payment, RoutingRule
from .verification.explain import RECOMMENDATION_LABELS
from .verification.routing import ROLE_LABELS


class DocumentSerializer(serializers.ModelSerializer):
    doc_type_label = serializers.CharField(source="get_doc_type_display", read_only=True)
    extracted = serializers.SerializerMethodField()

    class Meta:
        model = ClaimDocument
        fields = ["id", "doc_type", "doc_type_label", "file", "original_name", "size", "extraction_status",
                  "extraction_method", "extraction_error", "extracted", "uploaded_at"]

    def get_extracted(self, obj):
        data = dict(obj.extracted_data or {})
        sources = data.pop("_sources", {})
        return [{"key": k, "value": v, "source": sources.get(k, "")} for k, v in data.items() if v not in (None, "")]


class DocumentUploadSerializer(serializers.Serializer):
    file = serializers.FileField()
    doc_type = serializers.ChoiceField(choices=[c[0] for c in ClaimDocument._meta.get_field("doc_type").choices])

    def validate_file(self, f):
        ext = Path(f.name).suffix.lower()
        if ext not in settings.CLAIMS["ALLOWED_EXTENSIONS"]:
            raise serializers.ValidationError(f"Upload a PDF, image or text file. {ext or 'This file type'} isn't supported.")
        if f.size > settings.CLAIMS["MAX_UPLOAD_MB"] * 1024 * 1024:
            raise serializers.ValidationError(f"Files must be under {settings.CLAIMS['MAX_UPLOAD_MB']} MB.")
        return f


class FindingSerializer(serializers.ModelSerializer):
    kind_label = serializers.CharField(source="get_kind_display", read_only=True)
    policy_label = serializers.SerializerMethodField()
    related_claim_number = serializers.CharField(source="related_claim.claim_number", default=None, read_only=True)
    document_name = serializers.CharField(source="document.original_name", default=None, read_only=True)

    class Meta:
        model = Finding
        fields = ["id", "kind", "kind_label", "severity", "title", "explanation", "evidence", "policy", "policy_label",
                  "policy_excerpt", "related_claim", "related_claim_number", "document", "document_name"]

    def get_policy_label(self, obj):
        return f"{obj.policy.code} v{obj.policy.version} · {obj.policy.title}" if obj.policy else None


class StepSerializer(serializers.ModelSerializer):
    role_label = serializers.SerializerMethodField()
    approver_name = serializers.CharField(source="approver.full_name", default=None, read_only=True)
    acted_by_name = serializers.CharField(source="acted_by.full_name", default=None, read_only=True)
    status_label = serializers.CharField(source="get_status_display", read_only=True)

    class Meta:
        model = ApprovalStep
        fields = ["id", "round", "sequence", "role", "role_label", "approver", "approver_name", "acted_by_name",
                  "status", "status_label", "reason", "comment", "activated_at", "acted_at"]

    def get_role_label(self, obj):
        return ROLE_LABELS.get(obj.role, obj.role)


class EventSerializer(serializers.ModelSerializer):
    actor_name = serializers.CharField(source="actor.full_name", default="System", read_only=True)

    class Meta:
        model = ClaimEvent
        fields = ["id", "action", "message", "actor_name", "data", "created_at"]


class PaymentSerializer(serializers.ModelSerializer):
    net_amount = serializers.DecimalField(max_digits=12, decimal_places=2, read_only=True)
    is_delayed = serializers.BooleanField(read_only=True)
    days_overdue = serializers.IntegerField(read_only=True)
    method_label = serializers.CharField(source="get_method_display", read_only=True)
    status_label = serializers.CharField(source="get_status_display", read_only=True)
    initiated_by_name = serializers.CharField(source="initiated_by.full_name", default=None, read_only=True)

    class Meta:
        model = Payment
        fields = ["id", "approved_amount", "deductions", "deduction_reason", "net_amount", "method", "method_label",
                  "status", "status_label", "due_date", "initiated_at", "initiated_by_name", "paid_at",
                  "reference_number", "remarks", "is_delayed", "days_overdue"]


class PaymentRowSerializer(PaymentSerializer):
    claim_id = serializers.IntegerField(source="claim.id", read_only=True)
    claim_number = serializers.CharField(source="claim.claim_number", read_only=True)
    claim_title = serializers.CharField(source="claim.title", read_only=True)
    employee_name = serializers.CharField(source="claim.employee.full_name", read_only=True)

    class Meta(PaymentSerializer.Meta):
        fields = PaymentSerializer.Meta.fields + ["claim_id", "claim_number", "claim_title", "employee_name"]


class ClaimListSerializer(serializers.ModelSerializer):
    employee_name = serializers.CharField(source="employee.full_name", read_only=True)
    category_label = serializers.CharField(source="get_category_display", read_only=True)
    status_label = serializers.CharField(source="get_status_display", read_only=True)
    finding_count = serializers.IntegerField(read_only=True, default=0)
    waiting_on = serializers.SerializerMethodField()

    class Meta:
        model = Claim
        fields = ["id", "claim_number", "title", "category", "category_label", "amount", "approved_amount",
                  "expense_date", "status", "status_label", "risk_score", "risk_level", "employee", "employee_name",
                  "submitted_at", "created_at", "finding_count", "waiting_on", "vendor"]

    def get_waiting_on(self, obj):
        if obj.status != Claim.Status.UNDER_REVIEW:
            return None
        step = next((s for s in obj.steps.all() if s.round == obj.review_round and s.status == "PENDING"), None)
        if not step:
            return None
        return f"{ROLE_LABELS.get(step.role, step.role)}" + (f" · {step.approver.full_name}" if step.approver else "")


class ClaimDetailSerializer(serializers.ModelSerializer):
    employee_info = serializers.SerializerMethodField()
    category_label = serializers.CharField(source="get_category_display", read_only=True)
    status_label = serializers.CharField(source="get_status_display", read_only=True)
    documents = DocumentSerializer(many=True, read_only=True)
    findings = FindingSerializer(many=True, read_only=True)
    steps = serializers.SerializerMethodField()
    previous_steps = serializers.SerializerMethodField()
    events = EventSerializer(many=True, read_only=True)
    payment = serializers.SerializerMethodField()
    recommendation_label = serializers.SerializerMethodField()
    is_editable = serializers.BooleanField(read_only=True)
    permissions = serializers.SerializerMethodField()

    class Meta:
        model = Claim
        fields = [
            "id", "claim_number", "employee", "employee_info", "category", "category_label", "title", "description",
            "amount", "currency", "expense_date", "start_date", "end_date", "vendor", "invoice_number", "city",
            "status", "status_label", "review_round", "risk_score", "risk_level", "verification_level",
            "ai_recommendation", "recommendation_label", "verification_summary", "policy_snapshot", "verified_at",
            "approved_amount", "submitted_at", "decided_at", "created_at", "updated_at",
            "documents", "findings", "steps", "previous_steps", "events", "payment", "is_editable", "permissions",
        ]
        read_only_fields = [
            "claim_number", "employee", "status", "review_round", "risk_score", "risk_level", "verification_level",
            "ai_recommendation", "verification_summary", "policy_snapshot", "verified_at", "approved_amount",
            "submitted_at", "decided_at",
        ]

    def get_employee_info(self, obj):
        e = obj.employee
        return {"id": e.id, "name": e.full_name, "employee_id": e.employee_id, "grade": e.grade,
                "department": e.department, "designation": e.designation,
                "manager": e.manager.full_name if e.manager else None}

    def get_steps(self, obj):
        return StepSerializer([s for s in obj.steps.all() if s.round == obj.review_round], many=True).data

    def get_previous_steps(self, obj):
        return StepSerializer([s for s in obj.steps.all() if s.round < obj.review_round], many=True).data

    def get_payment(self, obj):
        payment = getattr(obj, "payment", None)
        return PaymentSerializer(payment).data if payment else None

    def get_recommendation_label(self, obj):
        return RECOMMENDATION_LABELS.get(obj.ai_recommendation, "")

    def get_permissions(self, obj):
        from .services import can_act

        user = self.context["request"].user
        is_owner = obj.employee_id == user.id
        finance = user.role in ("FINANCE", "ADMIN")
        return {
            "edit": is_owner and obj.is_editable,
            "submit": is_owner and obj.is_editable,
            "decide": can_act(user, obj.current_step()),
            "reverify": user.role in ("FINANCE", "ADMIN", "HR") and obj.status == Claim.Status.UNDER_REVIEW,
            "initiate_payment": finance and obj.status == Claim.Status.APPROVED,
            "complete_payment": finance and obj.status == Claim.Status.PAYMENT_INITIATED,
        }

    def validate(self, attrs):
        start = attrs.get("start_date", getattr(self.instance, "start_date", None))
        end = attrs.get("end_date", getattr(self.instance, "end_date", None))
        if start and end and end < start:
            raise serializers.ValidationError({"end_date": "End date can't be before the start date."})
        amount = attrs.get("amount")
        if amount is not None and amount <= 0:
            raise serializers.ValidationError({"amount": "Amount must be more than zero."})
        exp = attrs.get("expense_date")
        if exp and exp > timezone.localdate():
            raise serializers.ValidationError({"expense_date": "Expense date can't be in the future."})
        return attrs


class RoutingRuleSerializer(serializers.ModelSerializer):
    condition_label = serializers.CharField(source="get_condition_display", read_only=True)
    add_role_label = serializers.CharField(source="get_add_role_display", read_only=True)

    class Meta:
        model = RoutingRule
        fields = ["id", "name", "condition", "condition_label", "value", "add_role", "add_role_label", "is_active"]
