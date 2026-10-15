"""Media serializers for the API."""

from rest_framework import serializers

from app.models import (
    BasicMedia,
    Episode,
    Item,
    MediaTypes,
    Sources,
    Status,
)


class ItemSerializer(serializers.ModelSerializer):
    """Serializer for the Item model."""

    class Meta:
        """Meta options for ItemSerializer."""

        model = Item
        fields = [
            "id",
            "media_id",
            "source",
            "media_type",
            "title",
            "image",
            "season_number",
            "episode_number",
        ]


class MediaSerializer(serializers.ModelSerializer):
    """Serializer for tracking media items."""

    item = ItemSerializer(read_only=True)

    class Meta:
        """Meta options for MediaSerializer."""

        model = BasicMedia
        fields = [
            "id",
            "item",
            "status",
            "score",
            "progress",
            "notes",
            "start_date",
            "end_date",
            "created_at",
        ]
        read_only_fields = ["id", "created_at"]


class MediaCreateSerializer(serializers.Serializer):
    """Serializer for creating new media entries."""

    media_id = serializers.CharField()
    source = serializers.ChoiceField(choices=Sources.choices)
    media_type = serializers.ChoiceField(choices=MediaTypes.choices)
    season_number = serializers.IntegerField(required=False, allow_null=True)
    status = serializers.ChoiceField(choices=Status.choices, required=False)
    score = serializers.DecimalField(
        max_digits=3,
        decimal_places=1,
        required=False,
        allow_null=True,
    )
    progress = serializers.IntegerField(required=False, default=0)
    notes = serializers.CharField(required=False, allow_blank=True, default="")
    start_date = serializers.DateTimeField(required=False, allow_null=True)
    end_date = serializers.DateTimeField(required=False, allow_null=True)


class MediaUpdateSerializer(serializers.Serializer):
    """Serializer for updating existing media entries."""

    status = serializers.ChoiceField(choices=Status.choices, required=False)
    score = serializers.DecimalField(
        max_digits=3,
        decimal_places=1,
        required=False,
        allow_null=True,
    )
    progress = serializers.IntegerField(required=False)
    notes = serializers.CharField(required=False, allow_blank=True)
    start_date = serializers.DateTimeField(required=False, allow_null=True)
    end_date = serializers.DateTimeField(required=False, allow_null=True)


class ProgressSerializer(serializers.Serializer):
    """Serializer for progress increase/decrease operations."""

    operation = serializers.ChoiceField(choices=["increase", "decrease"])


class EpisodeCreateSerializer(serializers.Serializer):
    """Serializer for creating episode tracking entries."""

    media_id = serializers.CharField()
    season_number = serializers.IntegerField()
    episode_number = serializers.IntegerField()
    source = serializers.ChoiceField(choices=Sources.choices)
    end_date = serializers.DateTimeField(required=False, allow_null=True)


class EpisodeSerializer(serializers.ModelSerializer):
    """Serializer for the Episode model."""

    item = ItemSerializer(read_only=True)

    class Meta:
        """Meta options for EpisodeSerializer."""

        model = Episode
        fields = ["id", "item", "end_date", "created_at"]
