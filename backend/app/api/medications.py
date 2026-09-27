"""/api/medications — authoritative local terminology search."""
import sqlite3
from fastapi import APIRouter, Depends, Query
from app.core.config import settings
from app.core.security import get_current_user
from app.models import User
from app.services import medication_index

# This file provides the medication terminology endpoints used by MediExplain+.
# It allows authenticated users to search the local medication index, inspect
# terminology statistics and retrieve stored medication concepts. The compatibility
# helper keeps the terminology results in the format expected by the medication
# editor while avoiding any automatic suggestion of patient-specific doses.

router=APIRouter(prefix="/api/medications",tags=["medications"])

def _compat(item:dict)->dict:
    """Keep existing MedicationEditor fields while exposing richer metadata."""
    brands=[item["brand_name"]] if item.get("brand_name") else []
    return {
        **item,
        "generic_name":item.get("generic_name") or item.get("display_name"),
        "brand_names":brands,
        "category":item.get("dosage_form") or item.get("source"),
        "common_doses":[],  # Never suggest a patient's dose from reference data.
    }

@router.get("/suggest")
async def suggest_medications(
    q:str=Query(...,min_length=2),
    top_k:int=Query(5,ge=1,le=20),
    _:User=Depends(get_current_user),
):
    return [_compat(x) for x in medication_index.suggest(q,top_k)]

@router.get("/stats")
async def medication_stats(_:User=Depends(get_current_user)):
    return medication_index.stats()

@router.get("/all")
async def list_all(
    limit:int=Query(250,ge=1,le=2000),
    _:User=Depends(get_current_user),
):
    con=sqlite3.connect(settings.MEDICATION_DB_PATH)
    con.row_factory=sqlite3.Row
    try:
        rows=con.execute(
            "SELECT * FROM medication_concepts ORDER BY display_name LIMIT ?",(limit,)
        ).fetchall()
        return [_compat(dict(r)) for r in rows]
    finally:
        con.close()
