"""Live object-level privacy/security regression audit for MediExplain+ Final.

Prerequisites:
  backend running on http://127.0.0.1:8000
  demo users seeded (`python -m scripts.seed`)

The script creates temporary records, tests authorization boundaries, then
cleans them up. It never treats UI hiding as authorization evidence.
"""
from __future__ import annotations
import json, sqlite3, sys, time, uuid
from pathlib import Path
import httpx

BASE="http://127.0.0.1:8000"
ROOT=Path(__file__).resolve().parents[2]
DB=ROOT/"backend"/"data"/"mediexplain.db"
OUT=ROOT/"evaluation"/"results"/"privacy_audit_final.json"
OUT.parent.mkdir(parents=True,exist_ok=True)
results=[]

class Tokens:
    def __init__(self): self.cache={}
    def headers(self,email):
        if email not in self.cache:
            r=httpx.post(BASE+"/api/auth/login",data={"username":email,"password":"demo1234"},timeout=10)
            r.raise_for_status();self.cache[email]={"Authorization":"Bearer "+r.json()["access_token"]}
        return self.cache[email]
T=Tokens()

def check(name,condition,detail=""):
    condition=bool(condition)
    results.append({"name":name,"pass":condition,"detail":detail})
    print(("✓" if condition else "✗"),name,detail)

try:
    httpx.get(BASE+"/api/health",timeout=3).raise_for_status()
except Exception as exc:
    print("Backend unavailable:",exc);sys.exit(2)

doctor="doctor@demo.com";doctor2="doctor2@demo.com"
patient="patient.ur@demo.com";other_patient="patient.en@demo.com"
reviewer="reviewer@demo.com"
for email in (doctor,doctor2,patient,other_patient,reviewer):
    T.headers(email)

patients=httpx.get(BASE+"/api/users/patients",headers=T.headers(doctor)).json()
pid=next(x["id"] for x in patients if x["email"]==patient)

# 1 unauthenticated protection
r=httpx.get(BASE+"/api/consultations/")
check("Unauthenticated consultation list blocked",r.status_code in (401,403),str(r.status_code))

# 2 consent backend gate
r=httpx.post(BASE+"/api/consultations/",headers=T.headers(doctor),json={
    "patient_id":pid,"doctor_consent":False,"patient_consent":False,"patient_language":"ur"})
check("Consent cannot be bypassed",r.status_code==400,str(r.status_code))

# 3 create temporary owned consultation
r=httpx.post(BASE+"/api/consultations/",headers=T.headers(doctor),json={
    "patient_id":pid,"doctor_consent":True,"patient_consent":True,
    "patient_language":"ur","consent_method":"verbal"})
r.raise_for_status();cid=r.json()["id"]

# 4 other patient blocked
r=httpx.get(f"{BASE}/api/consultations/{cid}",headers=T.headers(other_patient))
check("Other patient object access blocked",r.status_code==403,str(r.status_code))

# 5 other treating doctor blocked before assignment
r=httpx.get(f"{BASE}/api/consultations/{cid}",headers=T.headers(doctor2))
check("Unassigned doctor object access blocked",r.status_code==403,str(r.status_code))

# 6 cross-check doctor blocked when unassigned
r=httpx.get(f"{BASE}/api/consultations/{cid}",headers=T.headers(reviewer))
check("Unassigned cross-check reviewer blocked",r.status_code==403,str(r.status_code))

# 7 patient draft visibility blocked
r=httpx.get(f"{BASE}/api/consultations/{cid}",headers=T.headers(patient))
check("Patient cannot read unreleased case",r.status_code==403,str(r.status_code))

# 8 unauthorized destructive mutation blocked
r=httpx.delete(
    f"{BASE}/api/consultations/{cid}",
    headers=T.headers(doctor2),
)
check(
    "Other doctor cannot delete another doctor's consultation",
    r.status_code==403,
    str(r.status_code),
)

# 9 unauthorized audio blocked before checking file existence
r=httpx.get(f"{BASE}/api/consultations/{cid}/audio-summary",headers=T.headers(other_patient))
check("Other patient cannot fetch case audio",r.status_code==403,str(r.status_code))

# 10 unauthorized PDF blocked
r=httpx.get(f"{BASE}/api/consultations/{cid}/pdf",headers=T.headers(other_patient))
check("Other patient cannot fetch case PDF",r.status_code==403,str(r.status_code))

# 11 share boundary requires RELEASED, not merely record existence
r=httpx.post(f"{BASE}/api/consultations/{cid}/share",headers=T.headers(doctor))
check("Share link blocked before release",r.status_code==409,str(r.status_code))

# 12 public self-registration ignores role escalation
email=f"security-{uuid.uuid4().hex[:10]}@example.com"
r=httpx.post(BASE+"/api/auth/register",json={
    "email":email,"full_name":"Security Test","password":"StrongTest123!",
    "role":"admin","preferred_language":"en"})
registered_role=r.json().get("role") if r.status_code==201 else None
check("Public registration cannot self-assign admin/doctor",r.status_code==201 and registered_role=="patient",
      f"status={r.status_code}, role={registered_role}")

# 13 reviewer gains access only through explicit assignment
doctors=httpx.get(BASE+"/api/users/doctors",headers=T.headers(patient)).json()
doctor2_id=next(x["id"] for x in doctors if x["email"]==doctor2)
r=httpx.post(BASE+"/api/cross-check/request",headers=T.headers(doctor),json={
    "consultation_id":cid,"reviewer_id":doctor2_id,"reason":"Security assignment test"})
check("Owner can create explicit reviewer assignment",r.status_code in (200,201),str(r.status_code))
r2=httpx.get(f"{BASE}/api/consultations/{cid}",headers=T.headers(doctor2))
check("Assigned reviewer can read assigned case",r2.status_code==200,str(r2.status_code))
r3=httpx.get(f"{BASE}/api/consultations/{cid}",headers=T.headers(reviewer))
check("Different reviewer remains blocked",r3.status_code==403,str(r3.status_code))

# 14 password hashes
con=sqlite3.connect(DB)
row=con.execute("SELECT hashed_password FROM users WHERE email=?",(doctor,)).fetchone()
check("Password stored as bcrypt hash",bool(row and row[0].startswith("$2")),row[0][:4] if row else "missing")

# 15 portable file references: no /Users/ absolute path in tracked consultation file fields
absolute=con.execute("""SELECT count(*) FROM consultations
    WHERE coalesce(audio_path,'') LIKE '/Users/%'
       OR coalesce(audio_summary_path,'') LIKE '/Users/%'
       OR coalesce(prescription_image_path,'') LIKE '/Users/%'""").fetchone()[0]
check("Stored clinical file references are portable",absolute==0,f"absolute={absolute}")

# Cleanup temporary user (created only for role-escalation test) after APIs are done with it.
security_uid=con.execute("SELECT id FROM users WHERE email=?",(email,)).fetchone()
con.close()

# 16 deletion
r=httpx.delete(f"{BASE}/api/consultations/{cid}",headers=T.headers(doctor))
check("Authorized erasure endpoint deletes case",r.status_code==204,str(r.status_code))
r2=httpx.get(f"{BASE}/api/consultations/{cid}",headers=T.headers(doctor))
check("Deleted case no longer retrievable",r2.status_code==404,str(r2.status_code))

# 17 audit retains minimal deletion event
con=sqlite3.connect(DB)
actions=[x[0] for x in con.execute(
    "SELECT action FROM audit_logs WHERE target_type='consultation' AND target_id=?",(cid,))]
check("Deletion audit evidence retained","consultation.deleted" in actions,str(actions[-6:]))
# test account has no clinical data; remove it to keep demo DB tidy
if security_uid:
    con.execute("DELETE FROM users WHERE id=?",(security_uid[0],));con.commit()
con.close()

# 18 invalid public token
r=httpx.get(BASE+"/api/share/not-a-valid-token")
check("Invalid share token rejected",r.status_code in (401,404),str(r.status_code))

passed=sum(x["pass"] for x in results)
result={"passed":passed,"total":len(results),"all_pass":passed==len(results),"checks":results}
OUT.write_text(json.dumps(result,indent=2))
print(f"\n{passed}/{len(results)} checks passed. Results: {OUT}")
sys.exit(0 if result["all_pass"] else 1)
