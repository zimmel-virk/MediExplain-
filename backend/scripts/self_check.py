#!/usr/bin/env python3
"""Non-destructive installation/integrity self-check for MediExplain+ Final."""
from __future__ import annotations
import json, shutil, sqlite3, subprocess
from pathlib import Path
from app.core.config import BASE_DIR, settings
from app.services.medication_index import stats

# This diagnostic script performs a non-destructive integrity check of the local
# MediExplain+ installation. It verifies the database and final Alembic schema,
# checks that stored file paths are portable, confirms medication terminology is
# populated, looks for required local tools such as Tesseract, Ollama, Node and
# npm, and confirms that the frontend package is present. It reports each result
# individually and returns a failing exit code only when a required core check
# does not pass.

checks=[]

def add(name, ok, detail=""):
    checks.append((name,bool(ok),str(detail)))
    print(("✓" if ok else "✗"), name, ("— "+str(detail) if detail else ""))

db=Path(str(settings.DATABASE_URL).replace("sqlite+aiosqlite:///",""))
add("Database exists",db.exists(),db)
if db.exists():
    con=sqlite3.connect(db)
    tables={x[0] for x in con.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    version=con.execute("SELECT version_num FROM alembic_version").fetchone() if "alembic_version" in tables else None
    add("Alembic final migration",bool(version and version[0]=="0003_schema_constraints"),version[0] if version else "missing")
    required={"users","consultations","consent_records","transcript_segments","safety_checks",
              "medication_concepts","consultation_medications","medication_schedules",
              "medication_events","translation_records","cross_checks","audit_logs"}
    add("Final schema tables",required.issubset(tables),f"{len(required & tables)}/{len(required)}")
    bad=con.execute("""SELECT count(*) FROM consultations
      WHERE coalesce(audio_path,'') LIKE '/Users/%'
         OR coalesce(audio_summary_path,'') LIKE '/Users/%'
         OR coalesce(prescription_image_path,'') LIKE '/Users/%'""").fetchone()[0]
    add("Portable stored paths",bad==0,f"absolute references={bad}")
    con.close()

m=stats()
add("Medication terminology populated",m["concepts"]>100,
    f"{m['concepts']} concepts / {m['aliases']} aliases; run scripts.setup_medication_data if empty")
add("Tesseract command",shutil.which("tesseract") is not None,shutil.which("tesseract") or "not installed")
add("Ollama command",shutil.which("ollama") is not None,shutil.which("ollama") or "not installed")
add("Node/npm",shutil.which("node") is not None and shutil.which("npm") is not None,
    f"node={shutil.which('node')} npm={shutil.which('npm')}")
add("Frontend package", (BASE_DIR.parent/"frontend"/"package.json").exists())

print("\nCore code self-check:",sum(x[1] for x in checks),"/",len(checks),"passed")
print("Some model/data checks may be pending until one-time setup downloads are complete.")
raise SystemExit(0 if all(ok for name,ok,detail in checks if name not in {"Medication terminology populated","Tesseract command"}) else 1)
