"""Search views for the API."""

from django.contrib.auth.decorators import login_not_required
from rest_framework import status
from rest_framework.decorators import api_view
from rest_framework.response import Response

from api.serializers.media import MediaSerializer
from api.serializers.search import SearchSerializer
from app import config
from app.helpers import enrich_items_with_user_data
from app.providers import services


@login_not_required
@api_view(["GET"])
def search(request):
    """Search for media across external providers."""
    serializer = SearchSerializer(data=request.query_params)
    if not serializer.is_valid():
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    data = serializer.validated_data
    source = data.get(
        "source",
        config.get_default_source_name(data["media_type"]).value,
    )
    results = services.search(
        data["media_type"],
        data["q"],
        data.get("page", 1),
        source,
    )

    if results.get("results"):
        enriched = enrich_items_with_user_data(
            request,
            results["results"],
            "search",
        )
        results["results"] = [
            {
                "item": entry["item"],
                "media": (
                    MediaSerializer(entry["media"]).data
                    if entry["media"] is not None
                    else None
                ),
            }
            for entry in enriched
        ]

    return Response(results)
