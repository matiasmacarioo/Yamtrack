from rest_framework import serializers


class SearchSerializer(serializers.Serializer):
    """Serializer for search query parameters."""

    q = serializers.CharField(required=True)
    media_type = serializers.ChoiceField(
        choices=[
            "tv",
            "movie",
            "anime",
            "manga",
            "game",
            "book",
            "comic",
            "boardgame",
        ],
    )
    source = serializers.CharField(required=False)
    page = serializers.IntegerField(required=False, default=1)
