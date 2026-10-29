
import pandas as pd

from app.config import DATA_DIR

INPUT_FILE = DATA_DIR / "lead_verification.csv"
OUTPUT_FILE = DATA_DIR / "manual_review_batch.csv"

APPROVED_COUNTRIES = {"US", "CA", "GB", "IE", "AU", "NZ", "SG"}


def has_text(series):
    return series.fillna("").astype(str).str.strip().ne("")


def build_review_batch():
    df = pd.read_csv(INPUT_FILE).fillna("")

    country = df["country_iso2"].str.upper().isin(APPROVED_COUNTRIES)

    recent = pd.to_numeric(df["content_count_30d"], errors="coerce").fillna(0)
    longform = pd.to_numeric(df["longform_count_60d"], errors="coerce").fillna(0)
    active = (recent >= 8) | (longform >= 2)

    email = has_text(df["description_emails"])
    links = has_text(df["description_links"])
    contact_candidate = email | links

    monetization = has_text(df["monetization_signals_detected"])
    need = has_text(df["need_signals_detected"])

    exclusion = df["possible_exclusion"].astype(str).str.lower().isin(
        {"true", "1", "yes"}
    )

    df["review_priority_score"] = (
        country.astype(int)
        + active.astype(int)
        + contact_candidate.astype(int) * 2
        + monetization.astype(int)
        + need.astype(int)
    )

    eligible_for_batch = country & active & contact_candidate & ~exclusion
    batch = df[eligible_for_batch].copy()

    batch = batch.sort_values(
        ["review_priority_score", "creator_name"],
        ascending=[False, True],
    ).head(25)

    batch["manual_review_status"] = "needs_manual_review"
    batch["qualification_status"] = "not_yet_qualified"

    columns = [
        "channel_id",
        "creator_name",
        "country_iso2",
        "profile_url",
        "channel_description",
        "subscribers",
        "last_content_date",
        "content_count_30d",
        "longform_count_60d",
        "description_emails",
        "description_links",
        "monetization_signals_detected",
        "monetization_evidence_suggestion",
        "need_signals_detected",
        "need_evidence_suggestion",
        "review_priority_score",
        "manual_review_status",
        "qualification_status",
    ]

    batch[columns].to_csv(OUTPUT_FILE, index=False)

    print("Candidates meeting batch filters:", len(df[eligible_for_batch]))
    print("Review batch exported:", len(batch))
    print("Output:", OUTPUT_FILE)
    print("All exported candidates remain unqualified pending verification.")


if __name__ == "__main__":
    build_review_batch()
