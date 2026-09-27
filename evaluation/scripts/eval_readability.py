"""
Evaluate patient-summary readability across consultations in your database.

Computes Flesch-Kincaid Grade Level, Flesch Reading Ease, and a few other
standard metrics for each English patient summary.

Run from project root:
    cd backend
    source .venv/bin/activate
    pip install textstat
    python ../evaluation/scripts/eval_readability.py

Output:
    evaluation/results/readability.json
    Console table
"""
import json
import sys
import sqlite3
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
DB   = ROOT / "backend" / "data" / "mediexplain.db"
OUT  = ROOT / "evaluation" / "results" / "readability.json"
OUT.parent.mkdir(parents=True, exist_ok=True)

try:
    import textstat
except ImportError:
    print("Install textstat first:  pip install textstat", file=sys.stderr)
    sys.exit(1)

if not DB.exists():
    print(f"Database not found at {DB}", file=sys.stderr)
    sys.exit(1)


conn = sqlite3.connect(DB)
rows = conn.execute("""
    SELECT id, patient_summary_en, doctor_edited_summary, status
    FROM consultations
    WHERE patient_summary_en IS NOT NULL
      AND length(patient_summary_en) > 30
""").fetchall()

if not rows:
    print("No consultations with summaries found. Create a few first.")
    sys.exit(0)


results = []
for cid, en_summary, edited, status in rows:
    text = edited if edited else en_summary
    results.append({
        "consultation_id": cid,
        "status": status,
        "word_count": textstat.lexicon_count(text, removepunct=True),
        "sentence_count": textstat.sentence_count(text),
        "flesch_kincaid_grade": round(textstat.flesch_kincaid_grade(text), 2),
        "flesch_reading_ease": round(textstat.flesch_reading_ease(text), 2),
        "gunning_fog": round(textstat.gunning_fog(text), 2),
        "smog": round(textstat.smog_index(text), 2),
        "text_preview": text[:120] + ("…" if len(text) > 120 else ""),
    })


# Aggregate
def stats(values):
    if not values: return {}
    s = sorted(values)
    return {
        "mean":   round(sum(s) / len(s), 2),
        "median": round(s[len(s)//2], 2),
        "min":    round(s[0], 2),
        "max":    round(s[-1], 2),
        "n": len(s),
    }

agg = {
    "flesch_kincaid_grade": stats([r["flesch_kincaid_grade"] for r in results]),
    "flesch_reading_ease":  stats([r["flesch_reading_ease"]  for r in results]),
    "gunning_fog":          stats([r["gunning_fog"]          for r in results]),
    "smog":                 stats([r["smog"]                 for r in results]),
    "word_count":           stats([r["word_count"]           for r in results]),
}

# How many summaries hit the ≤Grade 6 target?
at_target = sum(1 for r in results if r["flesch_kincaid_grade"] <= 6)
target_rate = at_target / len(results)

out = {
    "n_consultations": len(results),
    "target_grade_level": 6,
    "summaries_at_or_below_grade_6": at_target,
    "target_pass_rate": round(target_rate, 3),
    "aggregate": agg,
    "per_summary": results,
}
OUT.write_text(json.dumps(out, indent=2))


# Console output
print("\n" + "=" * 60)
print("Patient summary readability")
print("=" * 60)
print(f"Summaries analysed: {len(results)}")
print(f"Target: Flesch-Kincaid Grade Level ≤ 6")
print(f"At target: {at_target}/{len(results)} ({target_rate*100:.1f}%)")
print()
print(f"{'Metric':<26}  {'Mean':>7}  {'Median':>7}  {'Min':>6}  {'Max':>6}")
print("-" * 60)
for k, m in agg.items():
    print(f"{k:<26}  {m['mean']:>7}  {m['median']:>7}  {m['min']:>6}  {m['max']:>6}")
print()
print(f"Per-summary detail: {OUT.relative_to(ROOT)}")
