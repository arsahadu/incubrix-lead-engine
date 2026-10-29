
import pandas as pd

from app.config import DATA_DIR

INPUT_FILE = DATA_DIR / "enriched_creators.csv"
OUTPUT_FILE = DATA_DIR / "qualification_review.csv"

APPROVED_COUNTRIES = {"US", "CA", "GB", "IE", "AU", "NZ", "SG"}


def check_activity(row):
    """Check activity; long-form counts still need verification."""

    recent = pd.to_numeric(row.get("content_count_30d"), errors="coerce")
    longform = pd.to_numeric(row.get("longform_count_60d"), errors="coerce")

    if pd.notna(recent) and recent >= 8:
        return "pass"

    if pd.notna(longform) and longform >= 2:
        return "manual_review"

    return "fail"


def check_country(value):
    """Classify reported country; verify it using public evidence later."""

    if pd.isna(value) or not str(value).strip():
        return "unknown"

    country = str(value).strip().upper()

    if country in APPROVED_COUNTRIES:
        return "target_market"

    # The assessment allows up to 20% of leads from other markets.
    return "other_market"


def qualify_candidates():
    df = pd.read_csv(INPUT_FILE)
    results = []

    for _, row in df.iterrows():
        country_status = check_country(row.get("country_iso2"))
        activity_status = check_activity(row)
        reasons = []

        if country_status == "unknown":
            reasons.append("Country needs public verification")

        elif country_status == "other_market":
            reasons.append("Outside primary target markets; check market mix")

        if activity_status == "fail":
            reasons.append("Activity requirement not met")

        elif activity_status == "manual_review":
            reasons.append("Verify two qualifying long-form items")

        if row.get("enrichment_status") != "success":
            reasons.append("Enrichment unsuccessful")

        # Reject only when the activity check clearly fails.
        if activity_status == "fail":
            status = "rejected"
        elif (
            country_status == "unknown"
            or activity_status == "manual_review"
            or row.get("enrichment_status") != "success"
        ):
            status = "needs_manual_review"
        else:
            status = "initial_screen_passed"

        results.append({
            "channel_id": row["channel_id"],
            "creator_name": row["creator_name"],
            "profile_url": row["profile_url"],
            "country_iso2": row.get("country_iso2"),
            "content_count_30d": row.get("content_count_30d"),
            "longform_count_60d": row.get("longform_count_60d"),
            "country_status": country_status,
            "activity_status": activity_status,
            "candidate_status": status,
            "rejection_reason": "; ".join(reasons),
        })

    output = pd.DataFrame(results)
    output.to_csv(OUTPUT_FILE, index=False)

    print("\nInitial screening summary:")
    print(output["candidate_status"].value_counts().to_string())
    print(f"\nSaved review file: {OUTPUT_FILE}")


if __name__ == "__main__":
    qualify_candidates()
