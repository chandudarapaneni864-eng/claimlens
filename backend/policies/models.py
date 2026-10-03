from django.conf import settings
from django.db import models

CATEGORY_CHOICES = [
    ("travel", "Travel"),
    ("accommodation", "Accommodation"),
    ("food", "Food"),
    ("medical", "Medical"),
    ("other", "Other"),
]
POLICY_CATEGORY_CHOICES = CATEGORY_CHOICES + [("all", "All categories")]

DOCUMENT_TYPES = [
    ("invoice", "Invoice"),
    ("receipt", "Receipt"),
    ("bill", "Bill"),
    ("ticket", "Ticket"),
    ("payment_proof", "Payment proof"),
    ("approval", "Approval document"),
    ("medical_bill", "Medical bill"),
    ("prescription", "Prescription"),
    ("other", "Other"),
]
DOCUMENT_LABELS = dict(DOCUMENT_TYPES)


class Policy(models.Model):
    class Basis(models.TextChoices):
        PER_CLAIM = "per_claim", "Per claim"
        PER_DAY = "per_day", "Per day"
        PER_NIGHT = "per_night", "Per night"
        PER_MONTH = "per_month", "Per month"

    class Source(models.TextChoices):
        HR = "HR", "HR policy"
        FINANCE = "FINANCE", "Finance circular"
        ADMIN = "ADMIN", "Administration"

    code = models.CharField(max_length=40, help_text="Stable identifier shared by all versions, e.g. TRV-ACC")
    title = models.CharField(max_length=200)
    category = models.CharField(max_length=20, choices=POLICY_CATEGORY_CHOICES)
    version = models.PositiveIntegerField(default=1)
    source = models.CharField(max_length=20, choices=Source.choices, default=Source.HR)
    effective_from = models.DateField()
    effective_to = models.DateField(null=True, blank=True)
    applicable_grades = models.JSONField(default=list, blank=True, help_text="Empty list = all grades")
    applicable_departments = models.JSONField(default=list, blank=True, help_text="Empty list = all departments")
    limit_amount = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    limit_basis = models.CharField(max_length=20, choices=Basis.choices, default=Basis.PER_CLAIM)
    required_documents = models.JSONField(default=list, blank=True)
    preapproval_above = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    submission_window_days = models.PositiveIntegerField(null=True, blank=True)
    text = models.TextField(help_text="Full policy wording. It is split into chunks for retrieval.")
    is_active = models.BooleanField(default=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["category", "code", "-version"]
        unique_together = ("code", "version")
        verbose_name_plural = "policies"

    def __str__(self):
        return f"{self.code} v{self.version} · {self.title}"

    def covers_date(self, day):
        if day is None:
            return True
        if self.effective_from and day < self.effective_from:
            return False
        if self.effective_to and day > self.effective_to:
            return False
        return True

    def covers_person(self, grade, department):
        if self.applicable_grades and grade not in self.applicable_grades:
            return False
        if self.applicable_departments and department not in self.applicable_departments:
            return False
        return True


class PolicyChunk(models.Model):
    policy = models.ForeignKey(Policy, on_delete=models.CASCADE, related_name="chunks")
    index = models.PositiveIntegerField()
    text = models.TextField()
    embedding = models.JSONField(null=True, blank=True)

    class Meta:
        ordering = ["policy", "index"]

    def __str__(self):
        return f"{self.policy.code} v{self.policy.version} #{self.index}"
