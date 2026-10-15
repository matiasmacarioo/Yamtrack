"""History views for the API."""

import logging

from django.apps import apps
from django.contrib.auth.decorators import login_not_required
from rest_framework import status
from rest_framework.decorators import api_view
from rest_framework.response import Response

from app import history_processor
from app.models import BasicMedia

logger = logging.getLogger(__name__)


@login_not_required
@api_view(["GET"])
def history_list(request, source, media_type, media_id):
    """Get change history for a media item."""
    season_number = request.GET.get("season_number")
    episode_number = request.GET.get("episode_number")
    if season_number:
        season_number = int(season_number)
    if episode_number:
        episode_number = int(episode_number)

    user_medias = BasicMedia.objects.filter_media(
        request.user,
        media_id,
        media_type,
        source,
        season_number=season_number,
        episode_number=episode_number,
    )

    total_medias = user_medias.count()
    timeline = []
    for index, media in enumerate(user_medias, start=1):
        if history := media.history.all():
            media_entry_number = total_medias - index + 1
            timeline.extend(
                history_processor.process_history_entries(
                    history,
                    media_type,
                    media_entry_number,
                    request.user,
                ),
            )

    return Response(
        {
            "timeline": timeline,
            "total": total_medias,
        }
    )


@login_not_required
@api_view(["DELETE"])
def history_delete(request, media_type, history_id):
    """Delete a specific history record."""
    historical_model = apps.get_model(
        app_label="app",
        model_name=f"historical{media_type.lower()}",
    )
    try:
        historical_model.objects.get(
            history_id=history_id,
            history_user=request.user,
        ).delete()
        return Response(status=status.HTTP_204_NO_CONTENT)
    except historical_model.DoesNotExist:
        return Response(
            {"error": "Record not found."},
            status=status.HTTP_404_NOT_FOUND,
        )
