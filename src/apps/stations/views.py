from django.db.models import Q
from rest_framework import serializers, status
from rest_framework.decorators import api_view
from rest_framework.response import Response

from .models import BusStop


class StationListQuerySerializer(serializers.Serializer):
    q = serializers.CharField(required=False, allow_blank=True, default="")
    page = serializers.RegexField(r"\A[0-9]+\Z", required=False, default=1)
    page_size = serializers.RegexField(r"\A[0-9]+\Z", required=False, default=20)

    def validate_page(self, value):
        return self._positive_integer(value)

    def validate_page_size(self, value):
        page_size = self._positive_integer(value)
        if page_size > 100:
            raise serializers.ValidationError("Must be at most 100.")
        return page_size

    @staticmethod
    def _positive_integer(value):
        try:
            number = int(value)
        except ValueError:
            raise serializers.ValidationError("Must be a positive integer.")
        if number < 1:
            raise serializers.ValidationError("Must be a positive integer.")
        return number


class StationListItemSerializer(serializers.ModelSerializer):
    latitude = serializers.FloatField()
    longitude = serializers.FloatField()

    class Meta:
        model = BusStop
        fields = ("id", "name", "stop_number", "direction_label", "latitude", "longitude")


@api_view(["GET"])
def station_list(request):
    query = StationListQuerySerializer(data=request.query_params.dict())
    if not query.is_valid():
        return Response(
            {"code": "INVALID_REQUEST", "message": "요청 값을 확인해 주세요."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    search = query.validated_data["q"]
    page = query.validated_data["page"]
    page_size = query.validated_data["page_size"]

    stations = BusStop.objects.order_by("name", "id")
    if search:
        stations = stations.filter(Q(name__icontains=search) | Q(stop_number__icontains=search))

    count = stations.count()
    offset = (page - 1) * page_size
    results = stations[offset:offset + page_size] if offset < count else []
    return Response({
        "count": count,
        "page": page,
        "page_size": page_size,
        "results": StationListItemSerializer(results, many=True).data,
    })
