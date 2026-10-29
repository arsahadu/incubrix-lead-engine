import csv
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

import requests
from dotenv import load_dotenv

load_dotenv()

API_KEY = os.getenv("YOUTUBE_API_KEY")
BASE_URL = "https://www.googleapis.com/youtube/v3"

ROOT = Path(__file__).resolve().parent.parent
INPUT_FILE = ROOT / "data" / "discovered_creators.csv"
OUTPUT_FILE = ROOT / "data" / "enriched_creators.csv"

CACHE_DAYS = 7


def api_get(endpoint, params):
    """Call the YouTube Data API."""
    if not API_KEY:
        raise RuntimeError("YOUTUBE_API_KEY is missing from .env")

    response = requests.get(
        f"{BASE_URL}/{endpoint}",
        params={**params, "key": API_KEY},
        timeout=30,
    )
    response.raise_for_status()
    return response.json()


def get_channel_details(channel_ids):
    """Retrieve channel metadata in batches of 50."""
    channels = {}

    for start in range(0, len(channel_ids), 50):
        batch = channel_ids[start:start + 50]

        result = api_get("channels", {
            "part": "snippet,statistics,contentDetails",
            "id": ",".join(batch),
            "maxResults": 50,
        })

        for channel in result.get("items", []):
            snippet = channel.get("snippet", {})
            stats = channel.get("statistics", {})
            details = channel.get("contentDetails", {})

            channels[channel["id"]] = {
                "subscribers": stats.get("subscriberCount", ""),
                "country_iso2": snippet.get("country", ""),
                "description": snippet.get("description", ""),
                "uploads_playlist": (
                    details.get("relatedPlaylists", {}).get("uploads", "")
                ),
            }

    return channels


def get_recent_videos(playlist_id, cutoff):
    """Retrieve uploads published within the last 60 days."""
    videos = []
    page_token = None

    while playlist_id:
        params = {
            "part": "snippet,contentDetails",
            "playlistId": playlist_id,
            "maxResults": 50,
        }

        if page_token:
            params["pageToken"] = page_token

        result = api_get("playlistItems", params)
        reached_cutoff = False

        for item in result.get("items", []):
            snippet = item.get("snippet", {})
            published = snippet.get("publishedAt", "")

            if not published:
                continue

            published_at = datetime.fromisoformat(
                published.replace("Z", "+00:00")
            )

            if published_at < cutoff:
                reached_cutoff = True
                break

            video_id = (
                item.get("contentDetails", {}).get("videoId")
                or snippet.get("resourceId", {}).get("videoId")
            )

            if video_id:
                videos.append({
                    "video_id": video_id,
                    "published_at": published,
                    "url": f"https://www.youtube.com/watch?v={video_id}",
                })

        if reached_cutoff:
            break

        page_token = result.get("nextPageToken")
        if not page_token:
            break

    return videos


def get_video_durations(video_ids):
    """Retrieve video durations in batches of 50."""
    durations = {}

    for start in range(0, len(video_ids), 50):
        batch = video_ids[start:start + 50]

        result = api_get("videos", {
            "part": "contentDetails",
            "id": ",".join(batch),
            "maxResults": 50,
        })

        for video in result.get("items", []):
            duration = video.get("contentDetails", {}).get("duration", "")
            total_seconds = 0

            # Parse ISO 8601 durations such as PT12M30S.
            import re

            match = re.fullmatch(
                r"PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?",
                duration,
            )

            if match:
                hours, minutes, seconds = (
                    int(value or 0) for value in match.groups()
                )
                total_seconds = hours * 3600 + minutes * 60 + seconds

            durations[video["id"]] = total_seconds

    return durations


def load_existing():
    """Load previous results for cache reuse."""
    if not OUTPUT_FILE.exists():
        return {}

    with OUTPUT_FILE.open("r", newline="", encoding="utf-8") as file:
        return {
            row["channel_id"]: row
            for row in csv.DictReader(file)
            if row.get("channel_id")
        }


def is_cache_fresh(row, now):
    """Reuse only successful records enriched within seven days."""
    if row.get("enrichment_status") != "success":
        return False

    timestamp = row.get("enriched_at", "")

    if not timestamp:
        return False

    try:
        enriched_at = datetime.fromisoformat(timestamp)
        if enriched_at.tzinfo is None:
            enriched_at = enriched_at.replace(tzinfo=timezone.utc)

        return now - enriched_at < timedelta(days=CACHE_DAYS)

    except ValueError:
        return False


def enrich_creators():
    """Enrich new/stale channels and reuse fresh cached records."""
    with INPUT_FILE.open("r", newline="", encoding="utf-8") as file:
        candidates = list(csv.DictReader(file))

    # Keep one record per stable channel ID.
    unique_candidates = {
        row["channel_id"]: row
        for row in candidates
        if row.get("channel_id")
    }

    now = datetime.now(timezone.utc)
    existing = load_existing()

    fresh = {}
    stale = {}

    for channel_id, candidate in unique_candidates.items():
        cached = existing.get(channel_id)

        if cached and is_cache_fresh(cached, now):
            fresh[channel_id] = cached
        else:
            stale[channel_id] = candidate

    print(f"Total unique channels: {len(unique_candidates)}")
    print(f"Using fresh cache: {len(fresh)}")
    print(f"Need enrichment: {len(stale)}")

    # Fetch metadata only for channels needing enrichment.
    details_by_id = get_channel_details(list(stale))

    cutoff_30 = now - timedelta(days=30)
    cutoff_60 = now - timedelta(days=60)
    output = dict(fresh)

    for index, (channel_id, candidate) in enumerate(stale.items(), start=1):
        print(f"[{index}/{len(stale)}] {candidate.get('creator_name', '')}")

        details = details_by_id.get(channel_id, {})

        record = {
            **candidate,
            "subscribers": details.get("subscribers", ""),
            "country_iso2": details.get("country_iso2", ""),
            "channel_description": details.get("description", ""),
            "last_content_date": "",
            "recent_content_url": "",
            "content_count_30d": 0,
            "longform_count_60d": 0,
            "enrichment_status": "pending",
            "enrichment_error": "",
            "enriched_at": now.isoformat(),
        }

        try:
            playlist_id = details.get("uploads_playlist")

            if not playlist_id:
                record["enrichment_status"] = "no_uploads_playlist"
                output[channel_id] = record
                continue

            videos = get_recent_videos(playlist_id, cutoff_60)

            if videos:
                record["last_content_date"] = videos[0]["published_at"]
                record["recent_content_url"] = videos[0]["url"]

            record["content_count_30d"] = sum(
                datetime.fromisoformat(
                    video["published_at"].replace("Z", "+00:00")
                ) >= cutoff_30
                for video in videos
            )

            durations = get_video_durations([
                video["video_id"] for video in videos
            ])

            # Provisional metric only; the assessment does not
            # specify a precise long-form duration threshold.
            record["longform_count_60d"] = sum(
                durations.get(video["video_id"], 0) > 60
                for video in videos
            )

            record["enrichment_status"] = "success"

        except (requests.RequestException, ValueError, RuntimeError) as error:
            record["enrichment_status"] = "error"
            record["enrichment_error"] = str(error)
            print(f"  Error: {error}")

        output[channel_id] = record

    if output:
        fields = list(dict.fromkeys(
            key for row in output.values() for key in row
        ))

        with OUTPUT_FILE.open("w", newline="", encoding="utf-8") as file:
            writer = csv.DictWriter(file, fieldnames=fields)
            writer.writeheader()
            writer.writerows(output.values())

    print(f"\nChannels saved: {len(output)}")
    print(f"Output: {OUTPUT_FILE}")


if __name__ == "__main__":
    enrich_creators()
