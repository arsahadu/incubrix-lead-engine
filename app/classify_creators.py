
import pandas as pd
from pathlib import Path

DATA = Path("data")
SOURCE = DATA / "leads.csv"
ENRICHED = DATA / "enriched_creators.csv"
OUTPUT = DATA / "creator_classification_review.csv"

ORGANIZATION_TERMS = [
    "news network",
    "newsnation",
    "broadcast network",
    "radio-canada",
    "ohdio",
    "financial times",
    "department of",
    "university",
    "official channel",
    "media group",
    "publishing company",
]

AGENCY_TERMS = [
    "creator management",
    "influencer agency",
    "talent management",
    "marketing agency",
    "creator agency",
]


def clean(value):
    if pd.isna(value):
        return ""
    return str(value).strip()


def classify(name, description, segment):
    text = f"{name} {description}".lower()

    if any(term in text for term in AGENCY_TERMS):
        return "agency_review"

    if any(term in text for term in ORGANIZATION_TERMS):
        return "organization_review"

    if segment in {
        "podcaster",
        "educator",
        "expert_creator",
        "coach_consultant",
    }:
        return "potential_creator"

    return "manual_review"


def main():
    if not SOURCE.exists() or not ENRICHED.exists():
        raise SystemExit(
            "Missing data/leads.csv or data/enriched_creators.csv"
        )

    leads = pd.read_csv(SOURCE).fillna("")
    enriched = pd.read_csv(ENRICHED).fillna("")

    descriptions = (
        enriched[["channel_id", "channel_description"]]
        .drop_duplicates("channel_id")
        .rename(columns={"channel_id": "stable_creator_id"})
    )

    df = leads.merge(
        descriptions,
        on="stable_creator_id",
        how="left",
    )

    df["creator_type_review"] = df.apply(
        lambda row: classify(
            clean(row.get("creator_name", "")),
            clean(row.get("channel_description", "")),
            clean(row.get("creator_segment", "")),
        ),
        axis=1,
    )

    df["classification_note"] = (
        "Preliminary classification only; verify public profile manually."
    )

    df.to_csv(OUTPUT, index=False)

    print("Records reviewed:", len(df))
    print("Saved:", OUTPUT)
    print("\nClassification counts:")
    print(df["creator_type_review"].value_counts().to_string())

    print("\nPotential exclusions:")
    print(
        df.loc[
            df["creator_type_review"].isin(
                ["agency_review", "organization_review"]
            ),
            ["creator_name", "creator_type_review"],
        ].head(30).to_string(index=False)
    )


if __name__ == "__main__":
    main()
