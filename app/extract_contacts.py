
import re
import pandas as pd

from app.config import DATA_DIR

INPUT_FILE = DATA_DIR / "lead_verification.csv"
OUTPUT_FILE = DATA_DIR / "contact_review.csv"

EMAIL_PATTERN = r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}"



def classify_contact_links(links):
    links = str(links).lower()
    channels = []

    if "mailto:" in links or "contact" in links or "business" in links:
        channels.append("website_contact_candidate")

    if "instagram.com" in links:
        channels.append("instagram")

    if "linkedin.com" in links:
        channels.append("linkedin")

    if "wa.me/" in links or "whatsapp.com" in links:
        channels.append("whatsapp")

    if "linktr.ee" in links or "stan.store" in links:
        channels.append("creator_link_page")

    return "; ".join(channels)


def extract_contacts():
    df = pd.read_csv(INPUT_FILE).fillna("")

    # Reuse emails extracted from channel descriptions.
    description_emails = df.get(
        "description_emails", pd.Series("", index=df.index)
    )

    linked_text = df.get(
        "linked_page_text", pd.Series("", index=df.index)
    )

    df["public_emails"] = [
        "; ".join(sorted(
            set(
                re.findall(EMAIL_PATTERN, description)
                + re.findall(EMAIL_PATTERN, linked)
            ),
            key=str.lower,
        ))
        for description, linked in zip(description_emails, linked_text)
    ]

    df["contact_link_types"] = df.get(
        "description_links", pd.Series("", index=df.index)
    ).apply(classify_contact_links)

    df["contact_status"] = [
        "email_detected" if email
        else "public_contact_route_candidate" if channel
        else "manual_review"
        for email, channel in zip(
            df["public_emails"], df["contact_link_types"]
        )
    ]

    df.to_csv(OUTPUT_FILE, index=False)

    print("Candidates checked:", len(df))
    print("With public emails:", df["public_emails"].ne("").sum())
    print(
        "With potential contact links:",
        df["contact_link_types"].ne("").sum()
    )
    print("Saved:", OUTPUT_FILE)

if __name__ == "__main__":
    extract_contacts()
