import os
from datetime import timedelta

from django.conf import settings
from django.db import models
from django.utils import timezone

from policies.models import CATEGORY_CHOICES, DOCUMENT_TYPES


class Claim(models.Model):
    class Status(models.TextChoices):
        DRAFT = "DRAFT", "Draft"
        UNDER_REVIEW = "UNDER_REVIEW", "Under review"
        CORRECTION_REQUESTED = "CORRECTION_REQUESTED", "Correction requested"
        DOCS_REQUESTED = "DOCS_REQUESTED", "Documents requested"
        APPROVED = "APPROVED", "Approved"
        REJECTED = "REJECTED", "Rejected"
        PAYMENT_INITIATED = "PAYMENT_INITIATED", "Payment initiated"
        PAID = "PAID", "Settled"

    EDITABLE = {Status.DRAFT, Status.CORRECTION_REQUESTED, Status.DOCS_REQUESTED}

    claim_number = models.CharField(max_length=20, unique=True, null=True, blank=True)
    employee = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="claims")
    category = models.CharField(max_length=20, choices=CATEGORY_CHOICES)
    title = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    currency = models.CharField(max_length=3, default="INR")
    expense_date = models.DateField()
    start_date = models.DateField(null=True, blank=True)
    end_date = models.DateField(null=True, blank=True)
    vendor = models.CharField(max_length=200, blank=True)
    invoice_number = models.CharField(max_length=80, blank=True)
    city = models.CharField(max_length=100, blank=True)

    status = models.CharField(max_length=30, choices=Status.choices, default=Status.DRAFT)
    review_round = models.PositiveIntegerField(default=0)
    risk_score = models.PositiveIntegerField(default=0)
    risk_level = models.CharField(max_length=10, default="low")
    verification_level = models.CharField(max_length=60, blank=True)
    ai_recommendation = models.CharField(max_length=20, blank=True)
    verification_summary = models.TextField(blank=True)
    policy_snapshot = models.JSONField(default=dict, blank=True)
    verified_at = models.DateTimeField(null=True, blank=True)

    approved_amount = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    submitted_at = models.DateTimeField(null=True, blank=True)
    decided_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.claim_number or 'Draft'} · {self.title}"

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        if not self.claim_number:
            year = (self.created_at or timezone.now()).year
            self.claim_number = f"CLM-{year}-{self.pk:05d}"
            super().save(update_fields=["claim_number"])

    @property
    def is_editable(self):
        return self.status in self.EDITABLE

    @property
    def period_days(self):
        if self.start_date and self.end_date and self.end_date >= self.start_date:
            return (self.end_date - self.start_date).days + 1
        return 1

    @property
    def period_nights(self):
        if self.start_date and self.end_date and self.end_date > self.start_date:
            return (self.end_date - self.start_date).days
        return 1

    def current_step(self):
        return self.steps.filter(round=self.review_round, status=ApprovalStep.Status.PENDING).order_by("sequence").first()


def document_path(instance, filename):
    base, ext = os.path.splitext(filename)
    safe = "".join(ch for ch in base if ch.isalnum() or ch in "-_")[:60] or "document"
    stamp = timezone.now().strftime("%Y%m%d%H%M%S")
    return f"claims/{instance.claim.claim_number or instance.claim_id}/{instance.doc_type}_{stamp}_{safe}{ext.lower()}"


class ClaimDocument(models.Model):
    claim = models.ForeignKey(Claim, on_delete=models.CASCADE, related_name="documents")
    doc_type = models.CharField(max_length=20, choices=DOCUMENT_TYPES)
    file = models.FileField(upload_to=document_path, max_length=255)
    original_name = models.CharField(max_length=255)
    size = models.PositiveIntegerField(default=0)
    file_hash = models.CharField(max_length=64, db_index=True, blank=True)
    image_hash = models.CharField(max_length=32, blank=True)
    extracted_text = models.TextField(blank=True)
    extracted_data = models.JSONField(default=dict, blank=True)
    extraction_method = models.CharField(max_length=40, blank=True)
    extraction_status = models.CharField(max_length=12, default="pending")
    extraction_error = models.CharField(max_length=255, blank=True)
    uploaded_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL)
    uploaded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["uploaded_at"]

    def __str__(self):
        return f"{self.get_doc_type_display()} · {self.original_name}"


class Finding(models.Model):
    class Kind(models.TextChoices):
        MISMATCH = "MISMATCH", "Information mismatch"
        MISSING_INFO = "MISSING_INFO", "Missing information"
        MISSING_DOCUMENT = "MISSING_DOCUMENT", "Missing document"
        VIOLATION = "VIOLATION", "Policy violation"
        DUPLICATE = "DUPLICATE", "Possible duplicate"
        CONFLICT = "CONFLICT", "Policy conflict"
        OUTDATED_POLICY = "OUTDATED_POLICY", "Policy version change"
        UNREADABLE = "UNREADABLE", "Unreadable document"

    class Severity(models.TextChoices):
        LOW = "low", "Low"
        MEDIUM = "medium", "Medium"
        HIGH = "high", "High"

    claim = models.ForeignKey(Claim, on_delete=models.CASCADE, related_name="findings")
    kind = models.CharField(max_length=20, choices=Kind.choices)
    severity = models.CharField(max_length=10, choices=Severity.choices)
    title = models.CharField(max_length=200)
    explanation = models.TextField()
    evidence = models.JSONField(default=list, blank=True)
    policy = models.ForeignKey("policies.Policy", null=True, blank=True, on_delete=models.SET_NULL)
    policy_excerpt = models.TextField(blank=True)
    related_claim = models.ForeignKey(Claim, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    document = models.ForeignKey(ClaimDocument, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]


class ApprovalStep(models.Model):
    class Status(models.TextChoices):
        WAITING = "WAITING", "Waiting"
        PENDING = "PENDING", "Pending"
        APPROVED = "APPROVED", "Approved"
        REJECTED = "REJECTED", "Rejected"
        CORRECTION_REQUESTED = "CORRECTION_REQUESTED", "Correction requested"
        DOCS_REQUESTED = "DOCS_REQUESTED", "Documents requested"
        SKIPPED = "SKIPPED", "Skipped"

    claim = models.ForeignKey(Claim, on_delete=models.CASCADE, related_name="steps")
    round = models.PositiveIntegerField(default=1)
    sequence = models.PositiveIntegerField()
    role = models.CharField(max_length=20)
    approver = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="assigned_steps")
    acted_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    status = models.CharField(max_length=24, choices=Status.choices, default=Status.WAITING)
    reason = models.CharField(max_length=255, blank=True)
    comment = models.TextField(blank=True)
    activated_at = models.DateTimeField(null=True, blank=True)
    acted_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["round", "sequence"]


class ClaimEvent(models.Model):
    claim = models.ForeignKey(Claim, on_delete=models.CASCADE, related_name="events")
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL)
    action = models.CharField(max_length=40)
    message = models.TextField()
    data = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at", "id"]


class Payment(models.Model):
    class Status(models.TextChoices):
        PENDING = "PENDING", "Awaiting payment"
        INITIATED = "INITIATED", "Initiated"
        PAID = "PAID", "Paid"

    class Method(models.TextChoices):
        BANK = "bank_transfer", "Bank transfer"
        UPI = "upi", "UPI"
        PAYROLL = "payroll", "With salary"
        CHEQUE = "cheque", "Cheque"

    claim = models.OneToOneField(Claim, on_delete=models.CASCADE, related_name="payment")
    approved_amount = models.DecimalField(max_digits=12, decimal_places=2)
    deductions = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    deduction_reason = models.CharField(max_length=255, blank=True)
    method = models.CharField(max_length=20, choices=Method.choices, default=Method.BANK)
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.PENDING)
    due_date = models.DateField()
    initiated_at = models.DateTimeField(null=True, blank=True)
    initiated_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    paid_at = models.DateTimeField(null=True, blank=True)
    reference_number = models.CharField(max_length=80, blank=True)
    remarks = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    @property
    def net_amount(self):
        return self.approved_amount - (self.deductions or 0)

    @property
    def is_delayed(self):
        today = timezone.localdate()
        if self.status == self.Status.PAID:
            return bool(self.paid_at and timezone.localdate(self.paid_at) > self.due_date)
        return today > self.due_date

    @property
    def days_overdue(self):
        end = timezone.localdate(self.paid_at) if self.paid_at else timezone.localdate()
        return max(0, (end - self.due_date).days)

    @classmethod
    def due_from(cls, start):
        return timezone.localdate(start) + timedelta(days=settings.CLAIMS["PAYMENT_PERIOD_DAYS"])


class RoutingRule(models.Model):
    """Configurable rules that add approval levels. Manager and Finance are always in the chain."""

    class Condition(models.TextChoices):
        AMOUNT_GTE = "amount_gte", "Claim amount is at least"
        RISK_GTE = "risk_gte", "Risk score is at least"
        CATEGORY_IS = "category_is", "Category is"
        HAS_FINDING = "has_finding", "Has a finding of type"
        GRADE_IN = "grade_in", "Employee grade is one of"

    ROLE_CHOICES = [("DEPT_HEAD", "Department head"), ("HR", "HR"), ("FINANCE", "Finance")]

    name = models.CharField(max_length=120)
    condition = models.CharField(max_length=20, choices=Condition.choices)
    value = models.CharField(max_length=120, help_text="Number, category, finding type or comma-separated grades")
    add_role = models.CharField(max_length=20, choices=ROLE_CHOICES)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["add_role", "name"]

    def __str__(self):
        return self.name
