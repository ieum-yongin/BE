import re
from datetime import UTC

from django.db import transaction
from django.db.models import Count, Q
from django.utils import timezone
from rest_framework import serializers, status
from rest_framework.decorators import api_view, parser_classes
from rest_framework.exceptions import ParseError, UnsupportedMediaType
from rest_framework.parsers import JSONParser
from rest_framework.response import Response

from apps.pagination import PageQuerySerializer
from apps.stations.models import AnalysisRun

from .models import AlertDailyDetail, AlertReview, UsageAlert


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


class AlertDetailSerializer(AlertListItemSerializer):
    usage_ratio = serializers.SerializerMethodField()
    baseline_daily_usage = serializers.FloatField(allow_null=True)
    observed_daily_usage = serializers.FloatField(allow_null=True)

    def get_usage_ratio(self, alert):
        if alert.baseline_daily_usage and alert.observed_daily_usage is not None:
            return float(alert.observed_daily_usage / alert.baseline_daily_usage)
        return None

    class Meta(AlertListItemSerializer.Meta):
        fields = AlertListItemSerializer.Meta.fields + (
            "consecutive_days", "baseline_daily_usage", "observed_daily_usage",
            "expected_reason", "analysis_summary",
        )


class AlertDailyDetailSerializer(serializers.ModelSerializer):
    baseline_usage = serializers.FloatField(allow_null=True)

    class Meta:
        model = AlertDailyDetail
        fields = ("service_date", "baseline_usage", "observed_usage", "is_anomalous")


class AlertReviewSerializer(serializers.ModelSerializer):
    created_at = serializers.DateTimeField(default_timezone=UTC)

    class Meta:
        model = AlertReview
        fields = ("id", "alert_id", "status_after", "note", "created_at")


class AlertReviewRequestSerializer(serializers.Serializer):
    status_after = serializers.ChoiceField(choices=(
        UsageAlert.ReviewStatus.REVIEWING,
        UsageAlert.ReviewStatus.RESOLVED,
    ))
    note = serializers.CharField(allow_blank=True, allow_null=True, default=None, trim_whitespace=False)

    def validate_note(self, note):
        if note is None:
            return None
        try:
            byte_length = len(note.encode("utf-8"))
        except UnicodeEncodeError:
            raise serializers.ValidationError("유효한 메모 문자열을 입력해 주세요.") from None
        if not isinstance(self.initial_data["note"], str) or byte_length > 65_535:
            raise serializers.ValidationError("유효한 메모 문자열을 입력해 주세요.")
        return note


def latest_usage_alerts():
    analysis = AnalysisRun.latest_completed()
    return UsageAlert.objects.filter(analysis_id=analysis.pk) if analysis else UsageAlert.objects.none()


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

    alerts = latest_usage_alerts()
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


@api_view(["GET"])
def alert_detail(request, alert_id):
    alert_id = alert_id.lstrip("0")
    if not re.fullmatch(r"[0-9]+", alert_id) or request.query_params or request.body:
        return Response(
            {"code": "INVALID_REQUEST", "message": "요청 값을 확인해 주세요."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    alert = None
    if len(alert_id) <= 19:
        alert = latest_usage_alerts().select_related("station").filter(pk=int(alert_id)).first()
    if alert is None:
        return Response(
            {"code": "ALERT_NOT_FOUND", "message": "알림이 존재하지 않습니다."},
            status=status.HTTP_404_NOT_FOUND,
        )

    daily = AlertDailyDetail.objects.filter(alert_id=alert.pk).order_by("service_date")
    review = AlertReview.objects.filter(alert_id=alert.pk).order_by("-created_at", "-id").first()
    return Response({
        **AlertDetailSerializer(alert).data,
        "daily": AlertDailyDetailSerializer(daily, many=True).data,
        "latest_review": AlertReviewSerializer(review).data if review else None,
    })


@api_view(["POST"])
@parser_classes([JSONParser])
def alert_review_create(request, alert_id):
    alert_id = alert_id.lstrip("0")
    invalid_request = {"code": "INVALID_REQUEST", "message": "요청 값을 확인해 주세요."}
    try:
        data = request.data
    except ParseError:
        return Response(invalid_request, status=status.HTTP_400_BAD_REQUEST)
    except UnsupportedMediaType:
        return Response(
            {"code": "UNSUPPORTED_MEDIA_TYPE", "message": "JSON 형식으로 요청해 주세요."},
            status=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
        )

    payload = AlertReviewRequestSerializer(data=data)
    if not re.fullmatch(r"[0-9]+", alert_id) or request.query_params or not payload.is_valid():
        return Response(invalid_request, status=status.HTTP_400_BAD_REQUEST)

    with transaction.atomic():
        alert = None
        if len(alert_id) <= 19:
            alert = latest_usage_alerts().select_for_update().filter(pk=int(alert_id)).first()
        if alert is None:
            return Response(
                {"code": "ALERT_NOT_FOUND", "message": "알림이 존재하지 않습니다."},
                status=status.HTTP_404_NOT_FOUND,
            )

        review = AlertReview.objects.create(
            alert_id=alert.pk,
            created_at=timezone.now().replace(microsecond=0),
            **payload.validated_data,
        )
        alert.review_status = review.status_after
        alert.save(update_fields=["review_status"])

    return Response(AlertReviewSerializer(review).data, status=status.HTTP_201_CREATED)
