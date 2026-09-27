"""Summarise processing-time metadata from completed final-system consultations."""
import json, sqlite3, statistics
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]
DB=ROOT/"backend"/"data"/"mediexplain.db"
OUT=ROOT/"evaluation"/"results"/"performance.json"

con=sqlite3.connect(DB)
rows=con.execute("SELECT id, model_metadata FROM consultations WHERE model_metadata IS NOT NULL").fetchall()
con.close()

records=[]
for cid, raw in rows:
    try:
        meta=json.loads(raw) if isinstance(raw,str) else raw
    except Exception:
        continue
    if not isinstance(meta,dict):
        continue
    flat={"consultation_id":cid}
    for stage,value in meta.items():
        if isinstance(value,dict):
            for key,v in value.items():
                if isinstance(v,(int,float)) and (key=="seconds" or key.endswith("_seconds")):
                    flat[f"{stage}.{key}"]=float(v)
        elif isinstance(value,(int,float)) and stage.endswith("_seconds"):
            flat[stage]=float(value)
    records.append(flat)

keys=sorted({k for r in records for k in r if k!="consultation_id"})
def summary(key):
    vals=[r[key] for r in records if key in r]
    if not vals:return None
    return {"n":len(vals),"mean":round(statistics.mean(vals),3),
            "median":round(statistics.median(vals),3),
            "min":round(min(vals),3),"max":round(max(vals),3)}

result={"n_consultations":len(records),"timings":{k:summary(k) for k in keys},"per_consultation":records}
OUT.parent.mkdir(parents=True,exist_ok=True)
OUT.write_text(json.dumps(result,indent=2))
print(json.dumps({k:v for k,v in result.items() if k!="per_consultation"},indent=2))
