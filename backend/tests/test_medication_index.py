import sqlite3
import tempfile
import unittest
from pathlib import Path

from app.core.config import settings
from app.services import medication_index

# These unit tests check the local medication terminology matcher using a temporary
# database so the real project data is not changed. The tests confirm that a small
# medication-name typo can still recover the correct candidate, while generic form
# words and unrelated everyday words are rejected instead of being forced into a
# medication match.

class MedicationIndexTests(unittest.TestCase):
    def setUp(self):
        self.original = settings.MEDICATION_DB_PATH
        self.tmp = tempfile.TemporaryDirectory()
        settings.MEDICATION_DB_PATH = Path(self.tmp.name) / "meds.db"
        con = medication_index._connect()
        cur = con.execute(
            """INSERT INTO medication_concepts
               (source,source_id,display_name,normalized_name,tty,generic_name,country)
               VALUES('test','1','Metformin','metformin','IN','Metformin','test')"""
        )
        cid = cur.lastrowid
        con.execute(
            """INSERT INTO medication_aliases(concept_id,alias,normalized_alias,alias_type)
               VALUES(?,?,?,'generic')""",
            (cid, "Metformin", "metformin"),
        )
        con.execute(
            """INSERT INTO medication_concepts
               (source,source_id,display_name,normalized_name,tty,generic_name,country)
               VALUES('test','2','Paracetamol','paracetamol','IN','Paracetamol','test')"""
        )
        cid2=con.execute("SELECT id FROM medication_concepts WHERE source_id='2'").fetchone()[0]
        con.execute(
            """INSERT INTO medication_aliases(concept_id,alias,normalized_alias,alias_type)
               VALUES(?,?,?,'generic')""",
            (cid2, "Paracetamol", "paracetamol"),
        )
        con.commit()
        con.close()

    def tearDown(self):
        settings.MEDICATION_DB_PATH = self.original
        self.tmp.cleanup()

    def test_typo_recovers_candidate(self):
        out = medication_index.suggest("metfornin 500mg", top_k=3)
        self.assertTrue(out)
        self.assertEqual(out[0]["display_name"].lower(), "metformin")

    def test_form_word_is_not_a_drug(self):
        self.assertEqual(medication_index.suggest("tablet", top_k=3), [])

    def test_unrelated_word_not_forced(self):
        self.assertEqual(medication_index.suggest("breakfast", top_k=3), [])


if __name__ == "__main__":
    unittest.main()
