"""Idempotent data backfill for pre-final prototype rows."""
from pathlib import Path
import json
import sqlite3

# This file is used to migrate older MediExplain+ prototype data into the
# structure expected by the final system. It converts old absolute storage
# paths into portable references, creates missing consent records, preserves
# historical summary versions and reconstructs structured medication rows for
# consultations created before the newer database tables were introduced.
# The process is idempotent, so existing migrated records are checked before
# new rows are inserted and the backfill can be run again without duplicating
# the same historical data.


def _relative_ref(value: str | None, bucket: str) -> str | None:
    if not value:
        return value
    # Existing values can point to any historical Mac directory. Only the
    # basename is needed because uploaded/generated files live in fixed buckets.
    name = Path(value).name
    return f"{bucket}/{name}"

def run_legacy_backfill(db_path: Path) -> None:
    con = sqlite3.connect(db_path)
    con.row_factory = sqlite3.Row
    try:
        # Portable storage references.
        rows = con.execute(
            "SELECT id,audio_path,audio_summary_path,prescription_image_path FROM consultations"
        ).fetchall()
        for row in rows:
            con.execute(
                """UPDATE consultations
                   SET audio_path=?, audio_summary_path=?, prescription_image_path=?
                   WHERE id=?""",
                (
                    _relative_ref(row["audio_path"], "data/uploads"),
                    _relative_ref(row["audio_summary_path"], "audio_cache"),
                    _relative_ref(row["prescription_image_path"], "data/uploads"),
                    row["id"],
                ),
            )

        # Consent records for old cases.
        consultations = con.execute(
            """SELECT id,doctor_id,patient_id,doctor_consent,patient_consent,created_at
               FROM consultations"""
        ).fetchall()
        for c in consultations:
            exists = con.execute(
                "SELECT 1 FROM consent_records WHERE consultation_id=?", (c["id"],)
            ).fetchone()
            if not exists:
                con.execute(
                    """INSERT INTO consent_records
                       (consultation_id,doctor_id,patient_id,doctor_consent,patient_consent,
                        method,consent_version,granted_at)
                       VALUES(?,?,?,?,?,'verbal','legacy-1.0',?)""",
                    (
                        c["id"], c["doctor_id"], c["patient_id"],
                        c["doctor_consent"], c["patient_consent"], c["created_at"],
                    ),
                )

        # Preserve historical summary versions.
        for c in con.execute(
            "SELECT id,clinical_note,patient_summary_en,doctor_edited_summary,created_at FROM consultations"
        ).fetchall():
            for kind, content, source in (
                ("clinical_note", c["clinical_note"], "ai"),
                ("patient_summary", c["patient_summary_en"], "ai"),
                ("patient_summary", c["doctor_edited_summary"], "doctor"),
            ):
                if not content:
                    continue
                count = con.execute(
                    "SELECT COUNT(*) FROM summary_versions WHERE consultation_id=? AND kind=?",
                    (c["id"], kind),
                ).fetchone()[0]
                if source == "doctor" and count:
                    version = count + 1
                elif count:
                    continue
                else:
                    version = 1
                con.execute(
                    """INSERT OR IGNORE INTO summary_versions
                       (consultation_id,kind,version,content,source,approved,created_at)
                       VALUES(?,?,?,?,?,?,?)""",
                    (c["id"], kind, version, content, source, int(source == "doctor"), c["created_at"]),
                )

        # Backfill structured medications so the scheduler can work with old cases.
        for c in con.execute("SELECT id,structured_data FROM consultations").fetchall():
            if not c["structured_data"]:
                continue
            if con.execute(
                "SELECT 1 FROM consultation_medications WHERE consultation_id=? LIMIT 1",
                (c["id"],),
            ).fetchone():
                continue
            try:
                data = json.loads(c["structured_data"]) if isinstance(c["structured_data"], str) else c["structured_data"]
            except Exception:
                continue
            for idx, med in enumerate((data or {}).get("medications") or []):
                con.execute(
                    """INSERT INTO consultation_medications
                       (consultation_id,source,source_index,raw_name,canonical_name,strength,
                        dose,dose_unit,dosage_form,route,frequency,timing,food_instruction,
                        duration,as_needed,indication,notes,extraction_confidence,
                        match_confidence,doctor_confirmed)
                       VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (
                        c["id"], "legacy", idx, med.get("name_as_heard") or med.get("name"),
                        med.get("name"), med.get("strength"), med.get("dose"),
                        med.get("dose_unit"), med.get("dosage_form"), med.get("route"),
                        med.get("frequency"), med.get("timing"), med.get("food_instruction"),
                        med.get("duration"), int(bool(med.get("as_needed"))),
                        med.get("indication"), med.get("notes"), med.get("confidence"),
                        med.get("match_confidence"), int(bool(med.get("doctor_confirmed"))),
                    ),
                )

        con.commit()
    finally:
        con.close()
