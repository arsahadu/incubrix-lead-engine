
import pandas as pd

from app.config import DATA_DIR

INPUT_FILE = DATA_DIR / "enriched_creators.csv"
OUTPUT_FILE = DATA_DIR / "qualification_review.csv"

# Countries explicitly allowed by the assessment.
APPROVED_COUNTRIES = {
    "US", "CA", "GB", "IE", "AU", "NZ", "SG"
}


def check_activity(row):
    """Check the assessment's activity requirement."""

    recent = row.get("content_count_30d", 0)
    longform = row.get("longform_count_60d", 0)

    if pd.notna(recent) and recent >= 8:
        return "pass"

    # Duration threshold has not been specified by the assessment.
    # Do not treat the current duration-based count as final evidence.
    if pd.notna(longform) and longform >= 2:
        return "manual_review"

    return "fail"


def check_country(value):
    """Check whether the reported country is an approved market."""

    if pd.isna(value) or not str(value).strip():
        return "manual_review"

    if str(value).strip().upper() in APPROVED_COUNTRIES:
        return "pass"

    return "fail"


def qualify_candidates():
    df = pd.read_csv(INPUT_FILE)

    results = []

    for _, row in df.iterrows():
        country_status = check_country(row.get("country_iso2"))
        activity_status = check_activity(row)

        reasons = []

        if country_status == "fail":
            reasons.append("Country outside approved markets")

        elif country_status == "manual_review":
            reasons.append("Country missing or unverified")

        if activity_status == "fail":
            reasons.append("Activity requirement not met")

        elif activity_status == "manual_review":
            reasons.append("Long-form activity requires review")

        if row.get("enrichment_status") != "success":
            reasons.append("Enrichment unsuccessful")

        if reasons:
            status = "rejected" if (
                country_status == "fail"
                or activity_status == "fail"
            ) else "needs_manual_review"
        else:
            status = "activity_country_passed"

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

    print("\nCandidate screening summary:")
    print(output["candidate_status"].value_counts().to_string())
    print(f"\nSaved review file: {OUTPUT_FILE}")


if __name__ == "__main__":
    qualify_candidates()
