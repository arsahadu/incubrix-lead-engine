
import re
import pandas as pd

from app.config import DATA_DIR

INPUT_FILE = DATA_DIR / "lead_verification.csv"
CONTACT_FILE = DATA_DIR / "contact_review.csv"
QUEUE_FILE = DATA_DIR / "review_queue.csv"
OUTPUT_FILE = DATA_DIR / "leads.csv"

LEAD_COLUMNS = [
    "lead_id", "creator_name", "creator_segment", "country_iso2",
    "primary_language", "primary_platform", "profile_url",
    "stable_creator_id", "followers_or_subscribers", "last_content_date",
    "recent_content_url", "content_count_30d", "longform_count_60d",
    "monetization_signal", "monetization_evidence_url", "incubrix_need",
    "need_evidence_url", "best_channel", "channel_handle_or_url",
    "channel_evidence_url", "backup_channel", "personalization_hook",
    "first_message", "checked_date", "priority", "lead_score",
    "candidate_status", "rejection_reason",
]


def clean(value):
    if pd.isna(value):
        return ""
    return str(value).strip()


def classify_segment(row):
    text = (
        clean(row.get("creator_name", ""))
        + " "
        + clean(row.get("channel_description", ""))
        + " "
        + clean(row.get("video_title", ""))
    ).lower()

    # Avoid assigning a segment when the available evidence is weak.
    patterns = [
        ("podcaster", r"\bpodcast(?:er|ing)?\b"),
        ("educator", r"\b(teacher|educator|teaching|tutorial|course instructor)\b"),
        ("coach_consultant", r"\b(coach|consultant|consulting)\b"),
        ("expert_creator", r"\b(expert|professional training|masterclass)\b"),
    ]

    for segment, pattern in patterns:
        if re.search(pattern, text):
            return segment

    return "manual_review"


def export_leads():
    df = pd.read_csv(INPUT_FILE).fillna("")
    df = df.drop_duplicates(subset="channel_id", keep="first").copy()

    # Merge contact candidates, retaining every discovered channel.
    if CONTACT_FILE.exists():
        contacts = pd.read_csv(CONTACT_FILE).fillna("")
        contact_columns = [
            "channel_id", "public_emails", "contact_link_types",
            "contact_status",
        ]
        available = [c for c in contact_columns if c in contacts.columns]
        contacts = contacts[available].drop_duplicates("channel_id")
        if "public_emails" in contacts.columns:
            df = df.merge(
                contacts, on="channel_id", how="left",
                suffixes=("", "_contact"),
            )

    # Merge prioritization results.
    if QUEUE_FILE.exists():
        queue = pd.read_csv(QUEUE_FILE).fillna("")
        queue_columns = [
            "channel_id", "review_score", "review_group", "review_reason"
        ]
        available = [c for c in queue_columns if c in queue.columns]
        queue = queue[available].drop_duplicates("channel_id")
        df = df.merge(queue, on="channel_id", how="left")

    leads = pd.DataFrame(index=df.index)

    leads["lead_id"] = df["channel_id"]
    leads["creator_name"] = df["creator_name"]
    leads["creator_segment"] = df.apply(classify_segment, axis=1)
    leads["country_iso2"] = df["country_iso2"]
    # Discovery is English-focused, but language still needs verification.
    leads["primary_language"] = "English — verify"
    leads["primary_platform"] = "YouTube"
    leads["profile_url"] = df["profile_url"]
    leads["stable_creator_id"] = df["channel_id"]
    leads["followers_or_subscribers"] = df["subscribers"]
    leads["last_content_date"] = df["last_content_date"]
    leads["recent_content_url"] = df["recent_content_url"]
    leads["content_count_30d"] = df["content_count_30d"]
    leads["longform_count_60d"] = df["longform_count_60d"]

    # Signals are preliminary, not proof of qualification.
    detected_monetization = df["monetization_signals_detected"]
    existing_monetization = df["monetization_signal"]
    leads["monetization_signal"] = [
        clean(existing) or clean(detected)
        for existing, detected in zip(
            existing_monetization, detected_monetization
        )
    ]
    leads["monetization_evidence_url"] = df["monetization_evidence_url"]

    detected_need = df["need_signals_detected"]
    existing_need = df["incubrix_need"]
    leads["incubrix_need"] = [
        clean(existing) or (
            "Preliminary signal: " + clean(detected)
            if clean(detected) else ""
        )
        for existing, detected in zip(existing_need, detected_need)
    ]
    leads["need_evidence_url"] = df["need_evidence_url"]

    # Contact information is a candidate until suitability is verified.
    emails = df.get("public_emails", pd.Series("", index=df.index))
    links = df.get("description_links", pd.Series("", index=df.index))

    suggested_channels = df.get(
        "suggested_contact_channel",
        pd.Series("", index=df.index)
    )

    leads["best_channel"] = [
        "Email — verify suitability" if clean(email)
        else clean(suggested) if clean(suggested)
        else "Manual channel review"
        for email, suggested in zip(emails, suggested_channels)
    ]
    leads["channel_handle_or_url"] = [
        clean(email) or clean(link)
        for email, link in zip(emails, links)
    ]
    leads["channel_evidence_url"] = [
        clean(profile) if clean(email) else ""
        for profile, email in zip(df["profile_url"], emails)
    ]
    leads["backup_channel"] = ""

    leads["personalization_hook"] = [
        clean(suggested) or clean(existing)
        for suggested, existing in zip(
            df["suggested_personalization_hook"],
            df["personalization_hook"],
        )
    ]

    # No outreach message until qualification and contact checks are complete.
    leads["first_message"] = ""
    # Export date is not the evidence-check date; don't invent one.
    leads["checked_date"] = ""

    leads["priority"] = df.get(
        "review_group", pd.Series("", index=df.index)
    )
    leads["lead_score"] = df.get(
        "review_score", pd.Series("", index=df.index)
    )

    leads["candidate_status"] = "pending_verification"
    leads["rejection_reason"] = [
        "Possible exclusion — manual review" if str(flag).lower() in ("true", "1")
        else ""
        for flag in df["possible_exclusion"]
    ]

    leads = leads[LEAD_COLUMNS]
    leads.to_csv(OUTPUT_FILE, index=False)

    print("Unique creators exported:", len(leads))
    print("Unique lead IDs:", leads["lead_id"].nunique())
    print("High-priority review:",
          leads["priority"].eq("high_priority_review").sum())
    print("Creators with email candidates:",
          leads["best_channel"].str.startswith("Email", na=False).sum())
    print("Still pending verification:",
          leads["candidate_status"].eq("pending_verification").sum())
    print("Saved:", OUTPUT_FILE)
    print("Note: signals and contact routes are preliminary, not qualified leads.")


if __name__ == "__main__":
    export_leads()
