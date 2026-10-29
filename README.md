# IncuBrix Lead Generation Engine

A Python-based lead generation prototype that discovers potential creators, enriches their public profile data, identifies possible qualification signals, and prepares outreach drafts for review.

The goal is to make creator research more structured and reduce repetitive manual work while keeping lead verification and outreach decisions under human control.

## Features

- Discover potential creators using the YouTube Data API.
- Enrich creator profiles with channel information and recent activity.
- Identify possible monetization and workflow-need signals.
- Prioritize candidates for manual verification.
- Export candidate data and generate outreach message drafts.
- Record scheduling, tracking events, and simulated replies in a local test environment.

## Tech Stack

- **Language:** Python
- **Data processing:** pandas
- **Data collection:** YouTube Data API, requests, BeautifulSoup
- **Testing and local tracking:** pytest, FastAPI, SQLite
- **Version control:** Git and GitHub

## Project Structure

```text
lead/
├── app/
│   ├── config.py
│   ├── discover.py
│   ├── enrich.py
│   ├── verify.py
│   ├── qualify.py
│   ├── prioritize.py
│   ├── build_review_batch.py
│   ├── classify_creators.py
│   ├── extract_contacts.py
│   ├── export_leads.py
│   ├── generate_outreach.py
│   ├── test_mode.py
│   └── tracking.py
├── data/                  # Generated data and local test database
├── submission/
│   ├── market_research.md
│   └── 30_day_launch_plan.md
├── .env.example
├── .gitignore
├── requirements.txt
└── README.md
```

## Setup

Requires Python 3 and a YouTube Data API key.

1. Clone the repository and enter the project directory.

   ```bash
   git clone https://github.com/arsahadu/incubrix-lead-engine.git
   cd incubrix-lead-engine
   ```

2. Create and activate a virtual environment.

   ```bash
   python3 -m venv .venv
   source .venv/bin/activate
   ```

3. Install dependencies.

   ```bash
   pip install -r requirements.txt
   ```

4. Configure the required environment variables using `.env.example` as a reference. Keep API keys and other secrets in `.env`; never commit them to GitHub.

## Running the Pipeline

Run commands from the project root with the virtual environment activated.

```bash
python -m app.discover
python -m app.enrich
python -m app.verify
python -m app.prioritize
python -m app.extract_contacts
python -m app.qualify
python -m app.export_leads
python -m app.generate_outreach
```

Each stage performs a different part of the workflow. Run stages in the appropriate order because later stages depend on earlier outputs.

Discovery uses the YouTube Data API quota. Avoid rerunning discovery unnecessarily.

## Outputs

Generated files are stored in `data/`, including:

- `discovered_creators.csv` — discovered creator candidates.
- `enriched_creators.csv` — enriched profile and activity data.
- `lead_verification.csv` — verification fields and review signals.
- `leads.csv` — exported candidate records.
- `outreach_drafts.csv` — draft messages for manual review.

Additional review files may be generated during prioritization and qualification. The market research and launch plan are available in `submission/`.

## Local Test Mode

The project includes a local test workflow for recording scheduled jobs, tracking events, and simulated replies.

Initialize the test database:

```bash
python -m app.test_mode init
```

Check the recorded test events:

```bash
python -m app.test_mode status
```

The local tracking endpoint can be started with:

```bash
uvicorn app.tracking:app --reload
```

These tests demonstrate local event logging. They do not establish that messages are being sent or replies are being received through live outreach channels.

## Important Limitations

- Discovered candidates are not automatically qualified leads.
- Country, monetization, contact, and workflow-need evidence require verification.
- Outreach messages are drafts and must be reviewed before use.
- The current local test mode does not demonstrate a complete live integration across three outreach channels.
- Respect applicable privacy laws, marketing requirements, platform terms, and opt-out requests.

## Future Improvements

- Complete evidence-based qualification for target creators.
- Improve contact-route verification and personalization.
- Integrate and test approved outreach channels end to end.
- Measure campaign results and refine targeting using actual response data.