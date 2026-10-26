
import csv
import os
import re
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


def api_get(endpoint, params):
    """Call the YouTube Data API."""
    if not API_KEY:
        raise RuntimeError("YOUTUBE_API_KEY is missing from .env")

    params["key"] = API_KEY

    response = requests.get(
        f"{BASE_URL}/{endpoint}",
        params=params,
        timeout=30,
    )
    response.raise_for_status()
    return response.json()


def get_channel_details(channel_ids):
    """Retrieve metadata for channels in batches of 50."""
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
    """Fetch recent uploads and stop when they are older than 60 days."""
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
        stop = False

        for item in result.get("items", []):
            snippet = item.get("snippet", {})
            published = snippet.get("publishedAt", "")

            if not published:
                continue

            published_at = datetime.fromisoformat(
                published.replace("Z", "+00:00")
            )

            if published_at < cutoff:
                stop = True
                break

            video_id = (
                item.get("contentDetails", {}).get("videoId")
                or snippet.get("resourceId", {}).get("videoId")
            )

            if video_id:
                videos.append({
                    "video_id": video_id,
                    "title": snippet.get("title", ""),
                    "published_at": published,
                    "url": f"https://www.youtube.com/watch?v={video_id}",
                })

        if stop:
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
            match = re.fullmatch(
                r"PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?",
                duration,
            )

            if match:
                hours, minutes, seconds = (
                    int(value or 0) for value in match.groups()
                )
                durations[video["id"]] = (
                    hours * 3600 + minutes * 60 + seconds
                )

    return durations


def enrich_creators():
    """Enrich discoveries and save activity evidence."""
    with INPUT_FILE.open("r", newline="", encoding="utf-8") as file:
        candidates = list(csv.DictReader(file))

    channel_ids = list(dict.fromkeys(
        row["channel_id"] for row in candidates if row.get("channel_id")
    ))

    channel_details = get_channel_details(channel_ids)

    now = datetime.now(timezone.utc)
    cutoff_30 = now - timedelta(days=30)
    cutoff_60 = now - timedelta(days=60)

    enriched = []

    for index, row in enumerate(candidates, start=1):
        channel_id = row["channel_id"]
        details = channel_details.get(channel_id, {})

        print(f"[{index}/{len(candidates)}] {row['creator_name']}")

        record = {
            **row,
            "subscribers": details.get("subscribers", ""),
            "country_iso2": details.get("country_iso2", ""),
            "channel_description": details.get("description", ""),
            "last_content_date": "",
            "recent_content_url": "",
            "content_count_30d": 0,
            "longform_count_60d": 0,
            "enrichment_status": "pending",
            "enrichment_error": "",
        }

        try:
            uploads_playlist = details.get("uploads_playlist", "")

            if not uploads_playlist:
                record["enrichment_status"] = "no_uploads_playlist"
                enriched.append(record)
                continue

            videos = get_recent_videos(uploads_playlist, cutoff_60)

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

            record["longform_count_60d"] = sum(
                durations.get(video["video_id"], 0) > 60
                for video in videos
            )

            record["enrichment_status"] = "success"

        except (requests.RequestException, ValueError, RuntimeError) as error:
            record["enrichment_status"] = "error"
            record["enrichment_error"] = str(error)
            print(f"  Error: {error}")

        enriched.append(record)

    if enriched:
        OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)

        fields = list(dict.fromkeys(
            key for record in enriched for key in record
        ))

        with OUTPUT_FILE.open("w", newline="", encoding="utf-8") as file:
            writer = csv.DictWriter(file, fieldnames=fields)
            writer.writeheader()
            writer.writerows(enriched)

    print(f"\nChannels processed: {len(enriched)}")
    print(f"Output: {OUTPUT_FILE}")


if __name__ == "__main__":
    enrich_creators()
