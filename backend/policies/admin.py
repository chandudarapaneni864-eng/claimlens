from django.contrib import admin

from .models import Policy, PolicyChunk


class ChunkInline(admin.TabularInline):
    model = PolicyChunk
    extra = 0
    readonly_fields = ("index", "text")
    exclude = ("embedding",)


@admin.register(Policy)
class PolicyAdmin(admin.ModelAdmin):
    list_display = ("code", "version", "title", "category", "source", "limit_amount", "limit_basis", "effective_from", "effective_to", "is_active")
    list_filter = ("category", "source", "is_active")
    search_fields = ("code", "title", "text")
    inlines = [ChunkInline]
