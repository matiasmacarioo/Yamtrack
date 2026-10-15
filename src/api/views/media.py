"""Media CRUD and metadata views for the API."""

import logging

from django.apps import apps
from django.conf import settings
from django.contrib.auth.decorators import login_not_required
from django.core.cache import cache
from django.db import IntegrityError
from rest_framework import status
from rest_framework.decorators import api_view
from rest_framework.response import Response

from api.serializers.media import (
    MediaCreateSerializer,
    MediaSerializer,
    MediaUpdateSerializer,
    ProgressSerializer,
)
from app.forms import ManualItemForm, get_form_class
from app.helpers import get_owned_media_or_404
from app.models import (
    BasicMedia,
    Item,
    MediaTypes,
    Sources,
    Status,
)
from app.providers import services

logger = logging.getLogger(__name__)


@login_not_required
@api_view(["GET"])
def media_list(request, media_type):
    """List tracked media for a user, with optional filters."""
    status_filter = request.GET.get("status", "All")
    sort_filter = request.GET.get("sort")
    search_query = request.GET.get("search", "")

    valid_statuses = [
        "All",
        "Completed",
        "In progress",
        "Planning",
        "Paused",
        "Dropped",
    ]
    if status_filter not in valid_statuses:
        status_filter = "All"

    media_queryset = BasicMedia.objects.get_media_list(
        user=request.user,
        media_type=media_type,
        status_filter=status_filter,
        sort_filter=sort_filter,
        search=search_query,
    )

    BasicMedia.objects.annotate_max_progress(media_queryset, media_type)

    page = int(request.GET.get("page", 1))
    items_per_page = int(request.GET.get("per_page", 32))
    start = (page - 1) * items_per_page
    end = start + items_per_page
    total = len(media_queryset)
    page_items = media_queryset[start:end]

    serializer = MediaSerializer(page_items, many=True)
    return Response(
        {
            "count": total,
            "page": page,
            "per_page": items_per_page,
            "results": serializer.data,
        }
    )


@login_not_required
@api_view(["GET"])
def home(request):
    """Return in_progress and planning media for the home page."""
    sort_by = request.GET.get("sort", "upcoming")
    in_progress = BasicMedia.objects.get_home_status(
        user=request.user,
        status=Status.IN_PROGRESS.value,
        sort_by=sort_by,
    )
    planning = BasicMedia.objects.get_home_status(
        user=request.user,
        status=Status.PLANNING.value,
        sort_by=sort_by,
    )

    def serialize_section(section_data):
        result = {}
        for media_type, data in section_data.items():
            serializer = MediaSerializer(data["items"], many=True)
            result[media_type] = {
                "items": serializer.data,
                "total": data["total"],
            }
        return result

    return Response(
        {
            "in_progress": serialize_section(in_progress),
            "planning": serialize_section(planning),
        }
    )


@login_not_required
@api_view(["POST"])
def media_create(request, media_type):  # noqa: ARG001
    """Create a new media tracking entry from external metadata."""
    serializer = MediaCreateSerializer(data=request.data)
    if not serializer.is_valid():
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    data = serializer.validated_data
    season_number = data.get("season_number")
    season_numbers = [season_number] if season_number else None
    try:
        metadata = services.get_media_metadata(
            data["media_type"],
            data["media_id"],
            data["source"],
            season_numbers,
        )
    except services.ProviderAPIError:
        logger.exception("Failed to fetch metadata from provider.")
        return Response(
            {"error": "Failed to fetch metadata."},
            status=status.HTTP_404_NOT_FOUND,
        )
    item, _ = Item.objects.get_or_create(
        media_id=data["media_id"],
        source=data["source"],
        media_type=data["media_type"],
        season_number=season_number,
        defaults={"title": metadata["title"], "image": metadata["image"]},
    )
    model = apps.get_model(app_label="app", model_name=data["media_type"])
    instance_kwargs = {
        "item": item,
        "user": request.user,
        "status": data.get("status", Status.COMPLETED.value),
        "score": data.get("score"),
        "notes": data.get("notes", ""),
    }
    if not isinstance(getattr(model, "progress", None), property):
        instance_kwargs["progress"] = data.get("progress", 0)
    instance = model(**instance_kwargs)

    form_class = get_form_class(data["media_type"])
    if form_class is None:
        return Response(
            {"error": f"No form found for media type '{data['media_type']}'"},
            status=status.HTTP_400_BAD_REQUEST,
        )
    form_data = {
        "media_type": data["media_type"],
        "source": data["source"],
        "media_id": data["media_id"],
        "status": instance.status,
        "score": instance.score,
        "notes": instance.notes,
    }
    if not isinstance(getattr(model, "progress", None), property):
        form_data["progress"] = instance.progress
    if data.get("start_date") is not None:
        form_data["start_date"] = data["start_date"]
    if data.get("end_date") is not None:
        form_data["end_date"] = data["end_date"]
    form = form_class(form_data, instance=instance)
    if form.is_valid():
        try:
            form.save()
        except IntegrityError:
            return Response(
                {"error": "This media is already tracked."},
                status=status.HTTP_409_CONFLICT,
            )
        return Response(
            MediaSerializer(form.instance).data,
            status=status.HTTP_201_CREATED,
        )

    return Response(form.errors, status=status.HTTP_400_BAD_REQUEST)


@login_not_required
@api_view(["PATCH"])
def media_update(request, media_type, instance_id):
    """Update an existing media tracking entry."""
    media = get_owned_media_or_404(request, media_type, instance_id)
    serializer = MediaUpdateSerializer(data=request.data)
    if not serializer.is_valid():
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    for attr, value in serializer.validated_data.items():
        progress_is_property = isinstance(
            getattr(media.__class__, "progress", None),
            property,
        )
        if attr == "progress" and progress_is_property:
            if hasattr(media, "set_progress"):
                media.set_progress(value)
            continue
        setattr(media, attr, value)
    media.save()
    return Response(MediaSerializer(media).data)


@login_not_required
@api_view(["DELETE"])
def media_delete(request, media_type, instance_id):
    """Delete a media tracking entry."""
    media = get_owned_media_or_404(request, media_type, instance_id)
    media.delete()
    return Response(status=status.HTTP_204_NO_CONTENT)


@login_not_required
@api_view(["POST"])
def progress_edit(request, media_type, instance_id):
    """Increase or decrease progress on a media item."""
    media = get_owned_media_or_404(request, media_type, instance_id, prefetch=True)
    serializer = ProgressSerializer(data=request.data)
    if not serializer.is_valid():
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    if serializer.validated_data["operation"] == "increase":
        media.increase_progress()
    else:
        media.decrease_progress()

    media.refresh_from_db()
    return Response(MediaSerializer(media).data)


@login_not_required
@api_view(["PATCH"])
def update_score(request, media_type, instance_id):
    """Update the score for a media item."""
    media = get_owned_media_or_404(request, media_type, instance_id)
    score = request.data.get("score")
    if score is not None:
        media.score = float(score)
        media.save()
    return Response(MediaSerializer(media).data)


@login_not_required
@api_view(["POST"])
def sync_metadata(request, source, media_type, media_id):
    """Force refresh metadata from the external provider."""
    if source == Sources.MANUAL.value:
        return Response(
            {"error": "Manual items cannot be synced."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    cache_key = f"{source}_{media_type}_{media_id}"
    ttl = cache.ttl(cache_key)
    if ttl is not None and ttl > (settings.CACHE_TIMEOUT - 3):
        return Response(
            {"error": "Recently synced, please wait."},
            status=status.HTTP_429_TOO_MANY_REQUESTS,
        )

    cache.delete(cache_key)
    season_number = request.data.get("season_number")
    season_numbers = [season_number] if season_number else None
    metadata = services.get_media_metadata(
        media_type,
        media_id,
        source,
        season_numbers,
    )
    Item.objects.update_or_create(
        media_id=media_id,
        source=source,
        media_type=media_type,
        season_number=season_number,
        defaults={"title": metadata["title"], "image": metadata["image"]},
    )
    return Response({"message": f"{metadata['title']} synced successfully."})


@login_not_required
@api_view(["GET"])
def details(request, source, media_type, media_id):
    """Get metadata details and tracking info for a media item."""
    metadata = services.get_media_metadata(media_type, media_id, source)
    user_medias = BasicMedia.objects.filter_media_prefetch(
        request.user,
        media_id,
        media_type,
        source,
    )
    current_instance = user_medias[0] if user_medias else None

    data = {"metadata": metadata}
    if current_instance:
        data["tracking"] = MediaSerializer(current_instance).data

    return Response(data)


@login_not_required
@api_view(["GET"])
def season_details(request, source, media_id, season_number):
    """Get season metadata details and tracking info."""
    tv_with_seasons = services.get_media_metadata(
        "tv_with_seasons",
        media_id,
        source,
        [season_number],
    )
    season_metadata = tv_with_seasons[f"season/{season_number}"]
    user_medias = BasicMedia.objects.filter_media_prefetch(
        request.user,
        media_id,
        MediaTypes.SEASON.value,
        source,
        season_number=season_number,
    )
    current_instance = user_medias[0] if user_medias else None

    data = {"metadata": season_metadata, "tv": tv_with_seasons}
    if current_instance:
        data["tracking"] = MediaSerializer(current_instance).data
    return Response(data)


@login_not_required
@api_view(["GET", "POST"])
def create_entry(request):
    """Create a new manual media entry."""
    if request.method == "GET":
        return Response({"media_types": MediaTypes.values})

    form = ManualItemForm(request.data, user=request.user)
    if not form.is_valid():
        for field, errors in form.errors.items():
            for error in errors:
                logger.error("%s: %s", field, error)
        return Response(form.errors, status=status.HTTP_400_BAD_REQUEST)

    try:
        item = form.save()
    except IntegrityError:
        return Response(
            {"error": "Item already exists."},
            status=status.HTTP_409_CONFLICT,
        )

    updated_request = request.data.copy()
    updated_request.update({"source": item.source, "media_id": item.media_id})
    media_form = get_form_class(item.media_type)(updated_request)
    if not media_form.is_valid():
        item.delete()
        return Response(media_form.errors, status=status.HTTP_400_BAD_REQUEST)

    media_form.instance.user = request.user
    media_form.instance.item = item
    if item.media_type == MediaTypes.SEASON.value:
        media_form.instance.related_tv = form.cleaned_data["parent_tv"]
    elif item.media_type == MediaTypes.EPISODE.value:
        media_form.instance.related_season = form.cleaned_data["parent_season"]
    media_form.save()

    return Response(
        {"message": f"{item} added successfully."},
        status=status.HTTP_201_CREATED,
    )
