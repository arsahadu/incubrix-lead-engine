
# app/discover.py

import csv
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

import requests
from dotenv import load_dotenv

load_dotenv()

API_KEY = os.getenv("YOUTUBE_API_KEY")
API_URL = "https://www.googleapis.com/youtube/v3/search"

ROOT = Path(__file__).resolve().parent.parent
OUTPUT_FILE = ROOT / "data" / "discovered_creators.csv"

# Markets allowed by the assessment.
MARKETS = {
    "US": ["United States", "American"],
    "CA": ["Canada", "Canadian"],
    "GB": ["United Kingdom", "British"],
    "IE": ["Ireland", "Irish"],
    "AU": ["Australia", "Australian"],
    "NZ": ["New Zealand"],
    "SG": ["Singapore"],
}

# Focus on creators, not agencies or generic brands.
NICHES = [
    "educational creator online course",
    "business coach consultant creator",
    "expert video podcast",
]

FIELDS = [
    "channel_id",
    "creator_name",
    "profile_url",
    "video_url",
    "video_title",
    "video_published_at",
    "search_query",
    "discovery_region",
    "discovered_at",
]


def search_videos(query, country):
    """Search recent public videos using the official YouTube API."""

    if not API_KEY:
        raise RuntimeError("YOUTUBE_API_KEY is missing from .env")

    cutoff = (
        datetime.now(timezone.utc) - timedelta(days=60)
    ).strftime("%Y-%m-%dT%H:%M:%SZ")

    params = {
        "key": API_KEY,
        "part": "snippet",
        "q": query,
        "type": "video",
        "maxResults": 50,
        "order": "date",
        "publishedAfter": cutoff,
        "regionCode": country,
        "relevanceLanguage": "en",
    }

    response = requests.get(API_URL, params=params, timeout=30)
    response.raise_for_status()

    return response.json().get("items", [])


def discover_creators():
    """Discover unique channels across niches and target markets."""

    creators = {}
    today = datetime.now(timezone.utc).date().isoformat()

    for country, terms in MARKETS.items():
        for niche in NICHES:
            for term in terms:
                query = f"{niche} {term}"
                print(f"Searching {country}: {query}")

                try:
                    videos = search_videos(query, country)

                    for video in videos:
                        snippet = video.get("snippet", {})
                        video_id = video.get("id", {}).get("videoId")
                        channel_id = snippet.get("channelId")

                        if not video_id or not channel_id:
                            continue

                        if channel_id not in creators:
                            creators[channel_id] = {
                                "channel_id": channel_id,
                                "creator_name": snippet.get(
                                    "channelTitle", ""
                                ),
                                "profile_url": (
                                    "https://www.youtube.com/channel/"
                                    f"{channel_id}"
                                ),
                                "video_url": (
                                    f"https://www.youtube.com/watch?v={video_id}"
                                ),
                                "video_title": snippet.get("title", ""),
                                "video_published_at": snippet.get(
                                    "publishedAt", ""
                                ),
                                "search_query": query,
                                "discovery_region": country,
                                "discovered_at": today,
                            }

                except requests.RequestException as error:
                    print(f"  Search failed: {error}")

    return list(creators.values())


def save_candidates(candidates):
    """Merge new discoveries with existing records by channel ID."""

    OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    existing = {}

    if OUTPUT_FILE.exists():
        with OUTPUT_FILE.open(
            "r", newline="", encoding="utf-8"
        ) as file:
            for row in csv.DictReader(file):
                existing[row["channel_id"]] = row

    new_count = 0

    for candidate in candidates:
        channel_id = candidate["channel_id"]

        if channel_id not in existing:
            existing[channel_id] = candidate
            new_count += 1
        else:
            # Preserve the original record and add new discovery evidence.
            old = existing[channel_id]
            old_regions = set(
                filter(None, old.get("discovery_region", "").split(";"))
            )
            old_regions.add(candidate["discovery_region"])
            old["discovery_region"] = ";".join(sorted(old_regions))

    with OUTPUT_FILE.open(
        "w", newline="", encoding="utf-8"
    ) as file:
        writer = csv.DictWriter(file, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(existing.values())

    print(f"\nNew unique channels: {new_count}")
    print(f"Total unique channels: {len(existing)}")
    print(f"Saved to: {OUTPUT_FILE}")


if __name__ == "__main__":
    candidates = discover_creators()
    save_candidates(candidates)
