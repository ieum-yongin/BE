from django.db.models import Count, Q
from rest_framework import serializers, status
from rest_framework.decorators import api_view
from rest_framework.response import Response

from apps.pagination import PageQuerySerializer
from apps.stations.models import AnalysisRun

from .models import UsageAlert


class AlertListQuerySerializer(PageQuerySerializer):
    classification = serializers.ChoiceField(choices=UsageAlert.Classification.values, required=False)
    review_status = serializers.ChoiceField(choices=UsageAlert.ReviewStatus.values, required=False)


class AlertListItemSerializer(serializers.ModelSerializer):
    class StationSerializer(serializers.Serializer):
        id = serializers.IntegerField()
        name = serializers.CharField()

    station = StationSerializer()
    usage_ratio = serializers.FloatField(allow_null=True)

    class Meta:
        model = UsageAlert
        fields = (
            "id", "station", "change_start", "change_end", "change_direction",
            "classification", "review_status", "usage_ratio",
        )


@api_view(["GET"])
def alert_list(request):
    query = AlertListQuerySerializer(data=request.query_params.dict())
    if not query.is_valid():
        return Response(
            {"code": "INVALID_REQUEST", "message": "요청 값을 확인해 주세요."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    page = query.validated_data["page"]
    page_size = query.validated_data["page_size"]
    classification = query.validated_data.get("classification")
    review_status = query.validated_data.get("review_status")

    analysis = AnalysisRun.latest_completed()
    alerts = UsageAlert.objects.filter(analysis_id=analysis.id) if analysis else UsageAlert.objects.none()
    if review_status is not None:
        alerts = alerts.filter(review_status=review_status)

    counts = alerts.aggregate(
        total=Count("id"),
        needs_check=Count("id", filter=Q(classification=UsageAlert.Classification.NEEDS_CHECK)),
        expected=Count("id", filter=Q(classification=UsageAlert.Classification.EXPECTED)),
    )
    count = counts["total"]
    if classification is not None:
        count = counts[classification.lower()]
        alerts = alerts.filter(classification=classification)

    offset = (page - 1) * page_size
    results = []
    if offset < count:
        results = alerts.select_related("station").order_by("-change_end", "-id")[
            offset:offset + page_size
        ]

    return Response({
        "count": count,
        "page": page,
        "page_size": page_size,
        "counts": counts,
        "results": AlertListItemSerializer(results, many=True).data,
    })
