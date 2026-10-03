from rest_framework import serializers

from .models import Policy, PolicyChunk


class PolicyChunkSerializer(serializers.ModelSerializer):
    class Meta:
        model = PolicyChunk
        fields = ["id", "index", "text"]


class PolicySerializer(serializers.ModelSerializer):
    category_label = serializers.CharField(source="get_category_display", read_only=True)
    source_label = serializers.CharField(source="get_source_display", read_only=True)
    limit_basis_label = serializers.CharField(source="get_limit_basis_display", read_only=True)
    chunk_count = serializers.IntegerField(source="chunks.count", read_only=True)

    class Meta:
        model = Policy
        fields = [
            "id", "code", "title", "category", "category_label", "version", "source", "source_label",
            "effective_from", "effective_to", "applicable_grades", "applicable_departments",
            "limit_amount", "limit_basis", "limit_basis_label", "required_documents",
            "preapproval_above", "submission_window_days", "text", "is_active",
            "chunk_count", "created_at", "updated_at",
        ]
        read_only_fields = ["created_at", "updated_at"]

    def validate(self, attrs):
        start = attrs.get("effective_from", getattr(self.instance, "effective_from", None))
        end = attrs.get("effective_to", getattr(self.instance, "effective_to", None))
        if start and end and end < start:
            raise serializers.ValidationError({"effective_to": "End date must be on or after the start date."})
        return attrs


class PolicyDetailSerializer(PolicySerializer):
    chunks = PolicyChunkSerializer(many=True, read_only=True)

    class Meta(PolicySerializer.Meta):
        fields = PolicySerializer.Meta.fields + ["chunks"]
