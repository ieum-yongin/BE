from rest_framework import serializers


class PageQuerySerializer(serializers.Serializer):
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
