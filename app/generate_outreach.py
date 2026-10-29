
import pandas as pd
from pathlib import Path

DATA = Path("data")
OUTPUT = DATA / "outreach_drafts.csv"


def clean(value):
    if pd.isna(value):
        return ""
    return str(value).strip()

def make_safe_hook(row):
    hook = clean(row.get("personalization_hook", ""))
    evidence = (
        clean(row.get("need_evidence_url", ""))
        or clean(row.get("recent_content_url", ""))
    )

    if not hook or not evidence:
        return (
            "I came across your creator profile",
            "GENERIC_REVIEW_REQUIRED",
            evidence,
        )

    # Avoid copying long descriptions or entire paragraphs into outreach.
    hook = " ".join(hook.split())

    if len(hook) > 140:
        return (
            "I came across your creator profile",
            "HOOK_TOO_LONG_REVIEW_REQUIRED",
            evidence,
        )

    return f"I noticed {hook}", "REVIEW_HOOK_AND_EVIDENCE", evidence


def generate_messages(row):
    name = clean(row.get("creator_name", "")) or "there"
    hook = clean(row.get("personalization_hook", ""))
    profile = clean(row.get("profile_url", ""))
    need_evidence = clean(row.get("need_evidence_url", ""))
    video_url = clean(row.get("recent_content_url", ""))

    evidence_url = need_evidence or video_url

    # Keep personalization short and require manual evidence review.
    if not hook:
        opening = "I came across your creator profile"
        evidence_status = "GENERIC_REVIEW_REQUIRED"

    elif not evidence_url:
        opening = "I came across your creator profile"
        evidence_status = "MISSING_EVIDENCE_REVIEW_REQUIRED"

    elif len(" ".join(hook.split())) > 140:
        opening = "I came across your creator profile"
        evidence_status = "HOOK_TOO_LONG_REVIEW_REQUIRED"

    else:
        hook = " ".join(hook.split())
        opening = f"I noticed {hook}"
        evidence_status = "REVIEW_HOOK_AND_EVIDENCE"

    # Email draft
    email = (
        "Subject: Content workflow for your creator work\n\n"
        f"Hi {name},\n\n"
        f"{opening}. I'm reaching out from IncuBrix to ask whether "
        "content editing, repurposing, or publishing workflows are "
        "areas you're currently looking to improve.\n\n"
        "If it's relevant, would you be open to a brief introduction "
        "to IncuBrix? If not, just let me know and I won't follow up.\n\n"
        "Best,\n"
        "[Your name]\n"
        "IncuBrix\n\n"
        "If you prefer not to receive further outreach, reply "
        "'unsubscribe'."
    )

    # Instagram DM draft
    instagram = (
        f"Hey {name}! {opening}. I'm reaching out from IncuBrix "
        "to ask whether improving your content workflow is something "
        "you're exploring. Would you be open to hearing more? "
        "No worries if not — I won't follow up if you're not interested."
    )

    # LinkedIn draft
    linkedin = (
        f"Hi {name},\n\n"
        f"{opening}. I'm reaching out from IncuBrix to ask whether "
        "improving your content creation or repurposing workflow "
        "is a current priority.\n\n"
        "Would a short introduction be useful? Completely fine if "
        "this isn't relevant to you.\n\n"
        "[Your name]\n"
        "IncuBrix"
    )

    # Follow-up 1: gentle check-in
    follow1 = (
        f"Hi {name}, just following up on my earlier IncuBrix note. "
        "Are content editing or repurposing workflows a priority "
        "for you right now? No problem if not."
    )

    # Follow-up 2: final follow-up
    follow2 = (
        f"Hi {name}, one final follow-up from me. If improving your "
        "content workflow becomes relevant, you're welcome to reach "
        "out to IncuBrix. I'll leave it here after this message."
    )

    return {
        "email_draft": email,
        "instagram_draft": instagram,
        "linkedin_draft": linkedin,
        "first_message": email,
        "follow_up_1": follow1,
        "follow_up_2": follow2,
        "personalization_evidence_status": evidence_status,
        "personalization_evidence_url": evidence_url,
        "profile_reference": profile,
    }


def choose_channels(row):
    channel = clean(row.get("best_channel", "")).lower()
    url = clean(row.get("channel_handle_or_url", "")).lower()

    # Treat these as suggestions until manually verified.
    if "instagram.com" in url or "instagram" in channel:
        return "Instagram DM — verify", "Email — verify public business contact"

    if "linkedin.com" in url or "linkedin" in channel:
        return "LinkedIn — verify", "Email — verify public business contact"

    if "email" in channel or "@" in channel or "@" in url:
        return "Email — verify", "Creator-listed social channel — verify"

    return "Manual channel review", "Manual backup-channel review"


def main():
    source = DATA / "leads.csv"

    if not source.exists():
        raise SystemExit(
            "Missing data/leads.csv. Run python -m app.export_leads first."
        )

    df = pd.read_csv(source).fillna("")
    rows = []

    for _, row in df.iterrows():
        messages = generate_messages(row)
        best, backup = choose_channels(row)

        rows.append({
            "lead_id": clean(row.get("lead_id", "")),
            "creator_name": clean(row.get("creator_name", "")),
            "profile_url": clean(row.get("profile_url", "")),
            "candidate_status": clean(row.get("candidate_status", "")),
            "best_channel_suggestion": best,
            "backup_channel_suggestion": backup,
            **messages,
            "send_status": "DRAFT_ONLY_NOT_SENT",
        })

    result = pd.DataFrame(rows)
    result.to_csv(OUTPUT, index=False)

    print("Candidate drafts generated:", len(result))
    print("Unique lead IDs:", result["lead_id"].nunique())
    print(
        "Needs personalization review:",
        (result["personalization_evidence_status"] !=
         "REVIEW_HOOK_AND_EVIDENCE").sum()
    )
    print("Saved:", OUTPUT)
    print("Safety: drafts only; no messages were sent.")


if __name__ == "__main__":
    main()
