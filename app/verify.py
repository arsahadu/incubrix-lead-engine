
import re
from urllib.parse import urlparse, parse_qs, unquote

import pandas as pd
import requests
from bs4 import BeautifulSoup

from app.config import DATA_DIR

INPUT_FILE = DATA_DIR / "enriched_creators.csv"
REVIEW_FILE = DATA_DIR / "lead_verification.csv"

APPROVED_COUNTRIES = {"US", "CA", "GB", "IE", "AU", "NZ", "SG"}

CREATOR_KEYWORDS = [
    "creator", "youtube", "podcast", "educator", "teacher",
    "coach", "consultant", "course", "tutorial", "video",
]

MONETIZATION_KEYWORDS = [
    "course", "academy", "membership", "sponsor", "sponsorship",
    "paid", "consulting", "business enquiries", "business inquiries",
    "affiliate", "pricing", "enrol", "enroll", "subscription",
]

NEED_KEYWORDS = [
    "editing", "video editing", "repurpose", "repurposing",
    "captions", "subtitles", "content workflow",
    "video production", "shorts", "long-form", "long form",
    "upload schedule", "backlog", "content calendar",
    "content creation", "content strategy", "social media",
    "youtube automation", "podcast editing", "clip creation",
    "video clips", "batch content", "publishing schedule",
    "consistent uploads", "content team", "save time",
]

EXCLUSION_KEYWORDS = [
    # Media organizations and publishers
    "media organization",
    "media company",
    "news organization",
    "news network",
    "news channel",
    "newspaper",
    "newsroom",
    "broadcast network",
    "official news channel",
    "official channel for",

    # Agencies and intermediaries
    "talent agency",
    "talent management",
    "creator management agency",
    "influencer marketing agency",
    "social media agency",
    "video production agency",
    "video editing agency",
    "marketing agency",

    # Other ineligible account types
    "fan account",
    "fan page",
    "directory of creators",
    "creator directory",
]

EMAIL_PATTERN = re.compile(
    r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b",
    re.IGNORECASE,
)

URL_PATTERN = re.compile(r'https?://[^\s<>"\']+', re.IGNORECASE)

HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; PublicLeadResearch/1.0)"
}

# Keep website fetching limited and reuse results from previous runs.
MAX_LINKS_PER_CHANNEL = 2
REQUEST_TIMEOUT = 4


def clean_text(value):
    """Convert missing values to an empty string."""
    if pd.isna(value):
        return ""
    return str(value).strip()


def detect_signal(text, keywords):
    text = clean_text(text).lower()
    return "; ".join(word for word in keywords if word in text)


def extract_emails(text):
    """Extract publicly listed email addresses; do not test or email them."""
    return "; ".join(sorted(set(EMAIL_PATTERN.findall(clean_text(text)))))


def extract_urls(text):
    """Extract URLs from a public channel description."""
    urls = URL_PATTERN.findall(clean_text(text))
    cleaned = []

    for url in urls:
        url = url.rstrip(".,;)")
        url = url.replace("\\u0026", "&")
        url = url.replace("\\&", "&")

        # Resolve YouTube description redirect links to their destination.
        parsed = urlparse(url)

        if parsed.hostname and parsed.hostname.lower() in {
            "www.youtube.com", "youtube.com"
        } and parsed.path == "/redirect":
            destination = parse_qs(parsed.query).get("q", [""])[0]
            if destination.startswith(("http://", "https://")):
                url = unquote(destination)

        if url.startswith(("http://", "https://")) and url not in cleaned:
            cleaned.append(url)

    return cleaned



def fetch_public_page(url):
    """Read text from a publicly accessible HTML webpage."""
    try:
        response = requests.get(
            url,
            headers=HEADERS,
            timeout=REQUEST_TIMEOUT,
            allow_redirects=True,
        )

        content_type = response.headers.get("Content-Type", "").lower()

        if response.status_code != 200:
            print(f"HTTP {response.status_code}: {url}")
            return ""

        if "text/html" not in content_type:
            print(f"Not HTML ({content_type}): {url}")
            return ""

        soup = BeautifulSoup(response.text, "html.parser")

        for tag in soup(["script", "style", "noscript", "svg", "nav", "footer"]):
            tag.decompose()

        text = " ".join(soup.stripped_strings)[:12000]

        if not text.strip():
            print(f"No readable text: {url}")

        return text

    except requests.RequestException as exc:
        print(f"Request failed ({type(exc).__name__}): {url}")
        return ""



def create_review_file():
    source = pd.read_csv(INPUT_FILE).fillna({"channel_id": ""})

    # One row per stable channel ID.
    source = source.drop_duplicates(subset="channel_id", keep="first")

    # Load the previous file to preserve manual decisions and cached page text.
    if REVIEW_FILE.exists():
        old = pd.read_csv(REVIEW_FILE).fillna("")
        old = old.drop_duplicates(subset="channel_id", keep="last")
        old = old.set_index("channel_id")
    else:
        old = pd.DataFrame()

    columns = [
        "channel_id", "creator_name", "profile_url", "country_iso2",
        "channel_description", "subscribers", "last_content_date",
        "recent_content_url", "content_count_30d",
        "longform_count_60d", "video_title", "video_url",
        "enrichment_status",
    ]

    review = source[columns].copy()

    # Include useful existing metadata when available.
    for column in ["channel_description", "video_title"]:
        review[column] = review[column].fillna("")

    # Preserve previous manually entered values for review fields.
    review_fields = {
        "creator_relevant": "",
        "country_evidence_url": "",
        "country_evidence_source": "",
        "activity_evidence_url": "",
        "monetization_signal": "",
        "monetization_evidence_url": "",
        "incubrix_need": "",
        "need_evidence_url": "",
        "best_channel": "",
        "channel_handle_or_url": "",
        "channel_evidence_url": "",
        "backup_channel": "",
        "personalization_hook": "",
        "verification_status": "pending_review",
        "review_notes": "",
    }

    for column, default in review_fields.items():
        if column in old.columns:
            previous = old[column].reindex(review["channel_id"]).tolist()
        else:
            previous = [None] * len(review)

        current = (
            review[column].tolist()
            if column in review.columns
            else [default] * len(review)
        )

        review[column] = [
            prev if pd.notna(prev) and str(prev).strip() else cur
            for prev, cur in zip(previous, current)
        ]

    # Extract public information from descriptions.
    review["description_emails"] = review["channel_description"].apply(
        extract_emails
    )

    review["description_links"] = review["channel_description"].apply(
        lambda text: "; ".join(extract_urls(text))
    )

    # Reuse previously fetched public-page text when possible.
    cached_text = {}
    cached_urls = {}
    if (
        not old.empty
        and "channel_id" in old.columns
        and "linked_page_urls_checked" in old.columns
    ):
        cached_urls = old.set_index("channel_id")[
            "linked_page_urls_checked"
        ].to_dict()
    if not old.empty and "linked_page_text" in old.columns:
        cached_text = old["linked_page_text"].to_dict()


    page_texts = []
    checked_urls = []

    for _, row in review.iterrows():
        channel_id = row["channel_id"]
        description = clean_text(row["channel_description"])
        urls = extract_urls(description)[:MAX_LINKS_PER_CHANNEL]

        previous_text = clean_text(cached_text.get(channel_id, ""))
        previous_urls = clean_text(cached_urls.get(channel_id, ""))
        previously_checked = set(previous_urls.split("; ")) if previous_urls else set()

        if previous_text:
            page_text = previous_text
            checked = previous_urls
        else:
            page_parts = []
            checked_now = set(previously_checked)

            for url in urls:
                if url in previously_checked:
                    continue

                checked_now.add(url)
                text = fetch_public_page(url)

                if text:
                    page_parts.append(text)

            page_text = " ".join(page_parts)
            checked = "; ".join(sorted(checked_now))

        page_texts.append(page_text)
        checked_urls.append(checked)

    review["linked_page_text"] = page_texts
    review["linked_page_urls_checked"] = checked_urls


    # Combine available public text for preliminary signal detection.
    review["research_text"] = (
        review["channel_description"].fillna("")
        + " "
        + review["video_title"].fillna("")
        + " "
        + review["linked_page_text"].fillna("")
    )

    review["creator_relevance_signals"] = review["research_text"].apply(
        lambda text: detect_signal(text, CREATOR_KEYWORDS)
    )

    review["monetization_signals_detected"] = review["research_text"].apply(
        lambda text: detect_signal(text, MONETIZATION_KEYWORDS)
    )

    review["need_signals_detected"] = review["research_text"].apply(
        lambda text: detect_signal(text, NEED_KEYWORDS)
    )

    # Evidence suggestions only: these URLs must be checked by a human.
    # A linked page is a candidate source, not automatic proof of a claim.

    # Candidate source URLs only. These are not verified evidence.
    # Never use a generic profile URL as proof of a specific claim.
    def suggest_evidence_url(row, signal_column):
        if not clean_text(row[signal_column]):
            return ""

        page_text = clean_text(row["linked_page_text"])
        checked_urls = [
            url.strip()
            for url in clean_text(row["linked_page_urls_checked"]).split(";")
            if url.strip()
        ]

        # A linked page is only a source candidate if its text was fetched.
        # A human must still verify that the page supports the specific claim.
        if page_text and checked_urls:
            return checked_urls[0]

        return ""

    review["monetization_evidence_suggestion"] = review.apply(
        lambda row: suggest_evidence_url(
            row, "monetization_signals_detected"
        ),
        axis=1,
    )

    review["need_evidence_suggestion"] = review.apply(
        lambda row: suggest_evidence_url(
            row, "need_signals_detected"
        ),
        axis=1,
    )


    # Suggest a personalized hook from actual channel description text.
    def make_hook(row):
        description = clean_text(row["channel_description"])
        name = clean_text(row["creator_name"])

        if not description:
            return ""

        # Keep the suggestion grounded in the creator's own description.
        excerpt = re.sub(r"\s+", " ", description).strip()
        if len(excerpt) > 240:
            excerpt = excerpt[:237].rsplit(" ", 1)[0] + "..."

        return f"{name}: description mentions {excerpt}"

    review["suggested_personalization_hook"] = review.apply(
        make_hook, axis=1
    )

    # Do not qualify leads solely from keyword matches.
    exclusion_text = review["research_text"].fillna("").str.lower()

    review["possible_exclusion"] = exclusion_text.apply(
        lambda text: any(keyword in text for keyword in EXCLUSION_KEYWORDS)
    )

    review["country_in_target_market"] = (
        review["country_iso2"].fillna("").str.upper().isin(APPROVED_COUNTRIES)
    )

    review["activity_screen"] = "needs_review"

    recent_count = pd.to_numeric(
        review["content_count_30d"], errors="coerce"
    )
    longform_count = pd.to_numeric(
        review["longform_count_60d"], errors="coerce"
    )

    review.loc[
        recent_count >= 8, "activity_screen"
    ] = "activity_threshold_met"

    review.loc[
        (recent_count < 8) & (longform_count >= 2),
        "activity_screen"
    ] = "check_longform_definition"

    review.loc[
        (recent_count < 8) & (longform_count < 2),
        "activity_screen"
    ] = "activity_threshold_not_met"

    # Export research fields and evidence hints, but retain manual decisions.
    review = review.drop(columns=["research_text"])
    review.to_csv(REVIEW_FILE, index=False)

    print("Candidates prepared:", len(review))
    print("Public emails found:", int(review["description_emails"].ne("").sum()))
    print("Candidates with linked-page text:",
          int(review["linked_page_text"].ne("").sum()))
    print("Possible exclusions for review:",
          int(review["possible_exclusion"].sum()))
    print("Target-market candidates:",
          int(review["country_in_target_market"].sum()))
    print("Review file saved:", REVIEW_FILE)


if __name__ == "__main__":
    create_review_file()
