
import pandas as pd

from app.config import DATA_DIR

INPUT_FILE = DATA_DIR / "lead_verification.csv"
OUTPUT_FILE = DATA_DIR / "review_queue.csv"

APPROVED_COUNTRIES = {"US", "CA", "GB", "IE", "AU", "NZ", "SG"}

EXCLUSION_KEYWORDS = [
    "agency",
    "agencies",
    "directory",
    "fan account",
    "fan page",
    "management firm",
    "management company",
    "media network",
    "official channel",
]


def check_exclusion(name, description):
    text = f"{name} {description}".lower()
    return any(keyword in text for keyword in EXCLUSION_KEYWORDS)


def has_text(series):
    return series.fillna("").astype(str).str.strip().ne("")


def prioritize():
    df = pd.read_csv(INPUT_FILE)

    country = df["country_iso2"].fillna("").str.strip().str.upper()
    relevance = has_text(df["creator_relevance_signals"])
    monetization = has_text(df["monetization_signals_detected"])
    need = has_text(df["need_signals_detected"])

    # Evidence links are required before a signal earns evidence points.
    monetization_evidence = has_text(df["monetization_evidence_url"])
    need_evidence = has_text(df["need_evidence_url"])

    target_market = country.isin(APPROVED_COUNTRIES)

    df["review_score"] = (
        target_market.astype(int)
        + relevance.astype(int)
        + (monetization & monetization_evidence).astype(int) * 2
        + (need & need_evidence).astype(int) * 2
    )

    df["review_group"] = "manual_review"

    # High priority still means "inspect first", never "qualified".
    df.loc[
        target_market
        & relevance
        & monetization
        & monetization_evidence
        & need
        & need_evidence,
        "review_group",
    ] = "high_priority_review"

    descriptions = df["channel_description"].fillna("")
    df["possible_exclusion"] = [
        check_exclusion(name, description)
        for name, description in zip(df["creator_name"], descriptions)
    ]

    # Known organizational channels should be checked, not automatically
    # rejected solely because their name contains a broad keyword.
    df.loc[df["possible_exclusion"], "review_group"] = "exclusion_review"
    df.loc[df["possible_exclusion"], "review_score"] = 0

    df["review_reason"] = ""
    df.loc[target_market, "review_reason"] += "target_market; "
    df.loc[relevance, "review_reason"] += "creator_signal; "
    df.loc[monetization, "review_reason"] += "possible_monetization; "
    df.loc[monetization & ~monetization_evidence, "review_reason"] += (
        "missing_monetization_evidence; "
    )
    df.loc[need, "review_reason"] += "possible_need; "
    df.loc[need & ~need_evidence, "review_reason"] += "missing_need_evidence; "
    df.loc[~target_market, "review_reason"] += "country_unverified_or_out_of_market; "
    df.loc[df["possible_exclusion"], "review_reason"] += "possible_exclusion; "

    df["review_reason"] = df["review_reason"].str.rstrip("; ")

    df["_group_order"] = df["review_group"].map({
        "high_priority_review": 0,
        "manual_review": 1,
        "exclusion_review": 2,
    }).fillna(1)

    df = df.sort_values(
        ["_group_order", "review_score", "creator_name"],
        ascending=[True, False, True],
    ).drop(columns="_group_order")

    df.to_csv(OUTPUT_FILE, index=False)

    print("Total candidates:", len(df))
    print("Candidates with monetization evidence:",
          int((monetization & monetization_evidence).sum()))
    print("Candidates with need evidence:",
          int((need & need_evidence).sum()))
    print("High-priority review:", int(df["review_group"].eq(
        "high_priority_review").sum()))
    print("Manual review:", int(df["review_group"].eq("manual_review").sum()))
    print("Exclusion review:", int(df["review_group"].eq("exclusion_review").sum()))
    print(f"\nSaved: {OUTPUT_FILE}")
    print("Reminder: review priority does not mean the lead is qualified.")


if __name__ == "__main__":
    prioritize()
