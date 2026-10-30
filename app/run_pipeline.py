
import subprocess
import sys

PIPELINE = [
    ("Discover creators", "app.discover"),
    ("Enrich creator data", "app.enrich"),
    ("Verify candidates", "app.verify"),
    ("Prioritize candidates", "app.prioritize"),
    ("Extract contact candidates", "app.extract_contacts"),
    ("Qualify candidates", "app.qualify"),
    ("Export leads", "app.export_leads"),
    ("Generate outreach drafts", "app.generate_outreach"),
]


def main():
    print("\n========== INCUBRIX LEAD GENERATION ENGINE ==========\n")

    for index, (name, module) in enumerate(PIPELINE, start=1):
        print(f"\n[{index}/{len(PIPELINE)}] {name}")
        print("-" * 55, flush=True)

        try:
            subprocess.run(
                [sys.executable, "-m", module],
                check=True
            )
        except subprocess.CalledProcessError as error:
            print(f"\nFAILED: {name}")
            print(f"Exit code: {error.returncode}")
            print("Pipeline stopped. Fix the error before continuing.")
            sys.exit(error.returncode)

    print("\n========== PIPELINE COMPLETED ==========")
    print("Review generated CSV files before using them.")
    print("Candidates are not automatically qualified leads.")


if __name__ == "__main__":
    main()
