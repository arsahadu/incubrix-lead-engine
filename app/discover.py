import csv
import os
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import requests
from dotenv import load_dotenv

load_dotenv()

API_KEY = os.getenv("YOUTUBE_API_KEY")
API_URL = "https://www.googleapis.com/youtube/v3/search"

ROOT = Path(__file__).resolve().parent.parent
OUTPUT_FILE = ROOT / "data" / "discovered_creators.csv"
CHECKPOINT_FILE = ROOT / "data" / "discovery_checkpoint.txt"
MAX_SEARCHES_PER_RUN = 10

MARKETS = ["US", "CA", "GB", "IE", "AU", "NZ", "SG"]

# Target individual creators, not generic companies or news brands.
NICHES = [
    # Educators
    "independent online educator tutorial",
    "English teacher teaching lessons",
    "programming educator coding tutorials",
    "science educator explaining concepts",
    "online course instructor teaching",
    "language teacher lesson walkthrough",
    "career skills educator tutorials",

    # Coaches and expert-led creators
    "career coach advice",
    "business coach teaching entrepreneurs",
    "personal finance educator explaining",
    "leadership coach teaching skills",
    "fitness coach educational videos",
    "consultant explaining professional skills",

    # Podcasts and video-first creators
    "independent podcast host interview",
    "expert interview video podcast",
    "educational podcast host",
    "solo creator educational video essay",
    "creator explaining how they make videos",
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
    """Search recent videos through the official YouTube API."""
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

    for attempt in range(3):
        try:
            response = requests.get(
                API_URL, params=params, timeout=25
            )

            if response.status_code == 429:
                print("  Rate limited; skipping this query for now.")
                return []

            if response.status_code >= 500:
                if attempt < 2:
                    time.sleep(2 ** (attempt + 1))
                    continue

            response.raise_for_status()
            return response.json().get("items", [])

        except requests.HTTPError as error:
            # Never print the request URL: it contains the API key.
            status = (
                error.response.status_code
                if error.response is not None
                else "unknown"
            )
            try:
                reason = error.response.json()["error"]["errors"][0]["reason"]
            except (AttributeError, KeyError, IndexError, ValueError):
                reason = "unknown"

            print(f"  YouTube API error: HTTP {status}; reason={reason}")

            # Quota/authentication errors won't be fixed by retrying.
            if status in (400, 401, 403):
                break

            if attempt < 2:
                time.sleep(2 ** (attempt + 1))

        except requests.RequestException as error:
            # Print only the exception type to avoid exposing URL details.
            print(f"  Network error: {type(error).__name__}")
            if attempt < 2:
                time.sleep(2 ** (attempt + 1))

    raise RuntimeError("Search failed; checkpoint must not advance")



def discover_creators():
    """Discover unique channels and resume from the last completed query."""
    creators = {}
    today = datetime.now(timezone.utc).date().isoformat()

    # Load existing channels so checkpoint saves don't lose local state.
    if OUTPUT_FILE.exists():
        with OUTPUT_FILE.open("r", newline="", encoding="utf-8") as file:
            for row in csv.DictReader(file):
                creators[row["channel_id"]] = row

    # Resume from the next query after the last completed search.
    queries = [
        (country, niche)
        for country in MARKETS
        for niche in NICHES
    ]

    start_index = 0
    if CHECKPOINT_FILE.exists():
        try:
            start_index = int(
                CHECKPOINT_FILE.read_text(encoding="utf-8").strip()
            )
        except ValueError:
            start_index = 0

    end_index = min(start_index + MAX_SEARCHES_PER_RUN, len(queries))
    print(f"Starting at query {start_index + 1} of {len(queries)}")
    print(f"This run will attempt up to {end_index - start_index} searches")

    for index in range(start_index, end_index):
        country, niche = queries[index]
        print(f"Searching {country}: {niche}")

        try:
            videos = search_videos(niche, country)
        except RuntimeError as error:
            print(f"Stopping discovery: {error}")
            break   

        for video in videos:
            snippet = video.get("snippet", {})
            video_id = video.get("id", {}).get("videoId")
            channel_id = snippet.get("channelId")

            if not video_id or not channel_id:
                continue

            if channel_id not in creators:
                creators[channel_id] = {
                    "channel_id": channel_id,
                    "creator_name": snippet.get("channelTitle", ""),
                    "profile_url": (
                        "https://www.youtube.com/channel/" f"{channel_id}"
                    ),
                    "video_url": f"https://www.youtube.com/watch?v={video_id}",
                    "video_title": snippet.get("title", ""),
                    "video_published_at": snippet.get("publishedAt", ""),
                    "search_query": niche,
                    "discovery_region": country,
                    "discovered_at": today,
                }
            else:
                old = creators[channel_id]
                regions = set(
                    filter(None, old.get("discovery_region", "").split(";"))
                )
                regions.add(country)
                old["discovery_region"] = ";".join(sorted(regions))

        # Save accumulated results after every query.
        save_candidates(list(creators.values()))

        # Advance checkpoint only after this query has finished.
        CHECKPOINT_FILE.write_text(
            str(index + 1), encoding="utf-8"
        )

        time.sleep(1)

    print(f"Completed queries {start_index + 1} to {end_index}")
    print(f"Next checkpoint: {end_index}")
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
            old = existing[channel_id]
            old_regions = set(
                filter(None, old.get("discovery_region", "").split(";"))
            )
            old_regions.update(
                filter(None, candidate["discovery_region"].split(";"))
            )
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
