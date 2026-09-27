#!/usr/bin/env python3
"""Download/import real medication terminology used by MediExplain+.

Default:
  RxNorm Current Prescribable Content, pinned in app/core/config.py.
Optional:
  --drap-csv /path/to/export.csv for Pakistan brand enrichment.

The importer never supplies a prescribed dose. It is terminology verification only.
"""
import argparse

# This setup script populates the local medication terminology index used by
# MediExplain+. It imports the configured RxNorm prescribable-content dataset,
# optionally adds Pakistan-specific DRAP terminology from a supplied CSV, ensures
# the database is ready before import, and prints the resulting concept and alias
# statistics. The imported data is used for medication-name verification and
# matching only; it does not generate or infer prescribed doses or schedules.

from app.core.migrations import ensure_database
from app.services.medication_index import (
    download_and_ingest_rxnorm,
    ingest_drap_csv,
    stats,
)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--rxnorm-url", default=None)
    parser.add_argument("--skip-rxnorm", action="store_true")
    parser.add_argument("--drap-csv")
    args = parser.parse_args()

    ensure_database()

    if not args.skip_rxnorm:
        print("Importing RxNorm Current Prescribable Content...")
        print(download_and_ingest_rxnorm(args.rxnorm_url))

    if args.drap_csv:
        print("Importing optional DRAP export...")
        print(ingest_drap_csv(args.drap_csv))

    print("Medication index:", stats())


if __name__ == "__main__":
    main()
