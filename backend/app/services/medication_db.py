"""Compatibility facade for the final medication terminology index.

The former hand-built dictionary has been retired. All matching is now delegated
to the local RxNorm/optional-DRAP-backed medication_index service.
"""
from app.services.medication_index import suggest, stats


def all_medications(limit: int = 500) -> list[dict]:
    """Return terminology entries for legacy callers without inventing doses."""
    import sqlite3
    from app.core.config import settings

    con = sqlite3.connect(settings.MEDICATION_DB_PATH)
    con.row_factory = sqlite3.Row
    try:
        rows = con.execute(
            """SELECT id AS concept_id, source, source_id, display_name,
                      generic_name, brand_name, strength, dosage_form, route,
                      manufacturer
               FROM medication_concepts
               ORDER BY display_name
               LIMIT ?""",
            (int(limit),),
        ).fetchall()
        return [dict(row) | {"common_doses": []} for row in rows]
    finally:
        con.close()
