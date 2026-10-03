from django.contrib import admin

from .models import ApprovalStep, Claim, ClaimDocument, ClaimEvent, Finding, Payment, RoutingRule


class DocumentInline(admin.TabularInline):
    model = ClaimDocument
    extra = 0
    fields = ("doc_type", "file", "original_name", "extraction_status")
    readonly_fields = ("original_name", "extraction_status")


class FindingInline(admin.TabularInline):
    model = Finding
    fk_name = "claim"
    extra = 0
    fields = ("kind", "severity", "title")
    readonly_fields = fields


class StepInline(admin.TabularInline):
    model = ApprovalStep
    extra = 0
    fields = ("round", "sequence", "role", "approver", "status", "acted_by", "acted_at", "comment")


class EventInline(admin.TabularInline):
    model = ClaimEvent
    extra = 0
    fields = ("created_at", "actor", "action", "message")
    readonly_fields = fields


@admin.register(Claim)
class ClaimAdmin(admin.ModelAdmin):
    list_display = ("claim_number", "title", "employee", "category", "amount", "status", "risk_score", "submitted_at")
    list_filter = ("status", "category", "risk_level")
    search_fields = ("claim_number", "title", "vendor", "invoice_number")
    inlines = [DocumentInline, FindingInline, StepInline, EventInline]


@admin.register(Payment)
class PaymentAdmin(admin.ModelAdmin):
    list_display = ("claim", "approved_amount", "deductions", "status", "due_date", "paid_at", "reference_number")
    list_filter = ("status", "method")


@admin.register(RoutingRule)
class RoutingRuleAdmin(admin.ModelAdmin):
    list_display = ("name", "condition", "value", "add_role", "is_active")
