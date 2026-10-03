from datetime import date

from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from accounts.permissions import IsAdminRole

from . import rag
from .applicability import applicable_policies, detect_conflicts, knowledge_base_conflicts
from .models import DOCUMENT_TYPES, POLICY_CATEGORY_CHOICES, Policy
from .serializers import PolicyDetailSerializer, PolicySerializer


class PolicyViewSet(viewsets.ModelViewSet):
    queryset = Policy.objects.all()

    def get_serializer_class(self):
        return PolicyDetailSerializer if self.action == "retrieve" else PolicySerializer

    def get_permissions(self):
        if self.action in ("list", "retrieve", "search", "applicable", "meta", "conflicts"):
            return super().get_permissions()
        return [IsAdminRole()]

    def get_queryset(self):
        qs = super().get_queryset()
        category = self.request.query_params.get("category")
        if category:
            qs = qs.filter(category=category)
        return qs

    def perform_create(self, serializer):
        serializer.save(created_by=self.request.user)

    @action(detail=False, methods=["get"])
    def search(self, request):
        """RAG playground: show which policy passages a question retrieves."""
        query = request.query_params.get("q", "")
        return Response({"query": query, "results": rag.search(query, top_k=int(request.query_params.get("k", 5)))})

    @action(detail=False, methods=["get"])
    def applicable(self, request):
        """Which policies apply to a hypothetical claim (used live by the claim form)."""
        category = request.query_params.get("category", "other")
        on = request.query_params.get("date")
        try:
            on_date = date.fromisoformat(on) if on else date.today()
        except ValueError:
            on_date = date.today()
        grade = request.query_params.get("grade") or request.user.grade
        department = request.query_params.get("department") or request.user.department
        policies, superseded = applicable_policies(category, grade, department, on_date)
        return Response(
            {
                "applicable": PolicySerializer(policies, many=True).data,
                "superseded": PolicySerializer(superseded, many=True).data,
                "conflicts": detect_conflicts(policies),
            }
        )

    @action(detail=False, methods=["get"])
    def conflicts(self, request):
        return Response(knowledge_base_conflicts())

    @action(detail=False, methods=["get"])
    def meta(self, request):
        return Response(
            {
                "categories": [{"value": v, "label": l} for v, l in POLICY_CATEGORY_CHOICES],
                "document_types": [{"value": v, "label": l} for v, l in DOCUMENT_TYPES],
                "bases": [{"value": v, "label": l} for v, l in Policy.Basis.choices],
                "sources": [{"value": v, "label": l} for v, l in Policy.Source.choices],
            }
        )
