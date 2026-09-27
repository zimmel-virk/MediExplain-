"""Local, authoritative medication index backed by RxNorm and optional DRAP data."""
from __future__ import annotations
import csv
import hashlib
import io
import logging
import re
import sqlite3
import unicodedata
import urllib.request
import zipfile
from pathlib import Path
from difflib import SequenceMatcher
from app.core.config import settings

logger = logging.getLogger(__name__)

STRENGTH_RE = re.compile(r"\b(\d+(?:\.\d+)?)\s*(mg|mcg|µg|g|ml|%|iu|units?)\b", re.I)
FORM_WORDS = ("tablet","capsule","solution","suspension","syrup","injection","cream","ointment","gel","spray","drops","patch","powder")
# These terms are removed when trying to isolate a possible medicine name from
# longer medication instructions. They cover dosage forms, scheduling language,
# administration instructions and general clinical words that should not be
# mistaken for the actual drug name.
NON_DRUG_TERMS = {
    # Dosage forms / medication vocabulary that are not medicine names.
    "tablet",
    "tablets",
    "capsule",
    "capsules",
    "medicine",
    "medication",
    "dose",
    "doses",
    "syrup",
    "solution",
    "suspension",
    "injection",
    "cream",
    "ointment",
    "gel",
    "drops",
    "spray",
    "patch",
    "powder",

    # Frequency / schedule language.
    "once",
    "twice",
    "thrice",
    "daily",
    "weekly",
    "monthly",
    "morning",
    "afternoon",
    "evening",
    "night",
    "bedtime",
    "hour",
    "hours",
    "day",
    "days",
    "week",
    "weeks",
    "month",
    "months",
    "time",
    "times",
    "every",

    # Administration instructions.
    "after",
    "before",
    "with",
    "without",
    "food",
    "breakfast",
    "lunch",
    "dinner",
    "meal",
    "meals",
    "water",
    "take",
    "taking",
    "use",
    "using",

    # General clinical/UI words.
    "patient",
    "doctor",
    "prescription",
    "prescribed",
}


# These mappings handle common international naming differences before searching
# RxNorm. This lets terms commonly used outside the US, such as paracetamol or
# salbutamol, be matched against their corresponding RxNorm terminology.

INTERNATIONAL_NAME_EQUIVALENTS = {
    "paracetamol": "acetaminophen",
    "adrenaline": "epinephrine",
    "noradrenaline": "norepinephrine",
    "salbutamol": "albuterol",
    "lignocaine": "lidocaine",
    "frusemide": "furosemide",
}

# This function normalises terminology text before it is stored or compared.
# It standardises Unicode, converts text to lowercase, removes unnecessary
# punctuation and collapses repeated whitespace into a consistent search form.

def norm(text: str | None) -> str:
    s=unicodedata.normalize("NFKC", text or "").lower()
    s=re.sub(r"[^a-z0-9\u0600-\u06ff]+"," ",s)
    return re.sub(r"\s+"," ",s).strip()

# This function looks for a medication strength inside free text and returns
# the numeric value together with its recognised unit when one is present.
def extract_strength(text: str | None) -> str | None:
    m=STRENGTH_RE.search(text or "")
    return (m.group(1)+m.group(2).lower()) if m else None

# This function checks medication text for a recognised dosage form such as
# tablet, capsule, syrup, injection or cream.

def extract_form(text: str | None) -> str | None:
    n=norm(text)
    return next((f for f in FORM_WORDS if f in n.split()), None)

# This function removes strength values, dosage forms and common instruction
# words from a medication phrase so the remaining text is more likely to
# represent the medicine name itself.
def _clean_drug_name(text: str | None) -> str:
    """Remove strength, dosage form and administration words.

    This leaves only the portion that could plausibly represent
    a medicine name.
    """
    nq = norm(text)

    nq = re.sub(
        STRENGTH_RE,
        " ",
        nq,
    )

    tokens = [
        token
        for token in nq.split()
        if (
            token not in NON_DRUG_TERMS
            and not token.isdigit()
        )
    ]

    return " ".join(tokens).strip()

# This function converts a cleaned medication name into the terminology used
# for RxNorm searching. Known international equivalents are mapped directly,
# while a conservative similarity check allows small spelling differences
# without broadly rewriting unrelated clinical words.

def _canonical_query_name(text: str | None) -> str:
    """Convert international naming variants to RxNorm terminology.

    Exact known equivalents are converted directly. A conservative
    spelling check is also applied to the international term itself,
    allowing examples such as a minor typo of 'paracetamol' to map
    to RxNorm's 'acetaminophen' without inserting benchmark
    misspellings into the terminology database.
    """
    name = _clean_drug_name(text)

    if not name:
        return ""

    exact = INTERNATIONAL_NAME_EQUIVALENTS.get(
        name
    )

    if exact:
        return exact

    
    # This avoids rewriting arbitrary clinical phrases.
    if len(name.split()) == 1:

        for international_name, rxnorm_name in (
            INTERNATIONAL_NAME_EQUIVALENTS.items()
        ):
            if (
                name
                and international_name
                and name[0] == international_name[0]
            ):
                similarity = SequenceMatcher(
                    None,
                    name,
                    international_name,
                ).ratio()

                if similarity >= 0.88:
                    return rxnorm_name

    return name


# This function opens the local medication terminology database and creates
# the medication concept and alias tables when they do not already exist.
# Concepts store the main terminology record while aliases keep alternative
# names that can later be used during medication matching.
def _connect() -> sqlite3.Connection:
    p=Path(settings.MEDICATION_DB_PATH)
    p.parent.mkdir(parents=True, exist_ok=True)
    con=sqlite3.connect(p)
    con.row_factory=sqlite3.Row
    con.execute("""CREATE TABLE IF NOT EXISTS medication_concepts(
        id INTEGER PRIMARY KEY,
        source TEXT NOT NULL,
        source_id TEXT NOT NULL,
        display_name TEXT NOT NULL,
        normalized_name TEXT NOT NULL,
        tty TEXT,
        generic_name TEXT,
        brand_name TEXT,
        strength TEXT,
        dosage_form TEXT,
        route TEXT,
        active_ingredient TEXT,
        manufacturer TEXT,
        country TEXT,
        metadata_json TEXT,
        UNIQUE(source,source_id,display_name)
    )""")
    con.execute("""CREATE TABLE IF NOT EXISTS medication_aliases(
        id INTEGER PRIMARY KEY,
        concept_id INTEGER NOT NULL REFERENCES medication_concepts(id) ON DELETE CASCADE,
        alias TEXT NOT NULL,
        normalized_alias TEXT NOT NULL,
        alias_type TEXT DEFAULT 'synonym',
        UNIQUE(concept_id,normalized_alias)
    )""")
    con.commit()
    return con


# This function returns a small summary of the local terminology database,
# including the number of medication concepts, aliases and imported sources.
def stats() -> dict:
    con=_connect()
    try:
        return {
            "concepts": con.execute("SELECT count(*) FROM medication_concepts").fetchone()[0],
            "aliases": con.execute("SELECT count(*) FROM medication_aliases").fetchone()[0],
            "sources": [r[0] for r in con.execute("SELECT DISTINCT source FROM medication_concepts ORDER BY source")],
        }
    finally: con.close()


# This function imports medication terminology from an RxNorm archive.
# It reads RXNCONSO.RRF, keeps the relevant English RxNorm records, selects a
# preferred display entry for each concept and stores the remaining names as
# aliases. Strength and dosage-form information are also extracted where possible.
def ingest_rxnorm_zip(zip_path: str | Path) -> dict:
    """Import RXNCONSO.RRF from RxNorm Current Prescribable Content."""
    zpath=Path(zip_path)
    con=_connect()
    inserted=0
    aliases=0
    with zipfile.ZipFile(zpath) as z:
        member=next((n for n in z.namelist() if n.upper().endswith("RXNCONSO.RRF")), None)
        if not member:
            raise ValueError("RXNCONSO.RRF not found in RxNorm archive")
        # RRF delimiter is |; relevant columns follow the official RRF layout.
        by_cui={}
        with z.open(member) as raw:
            for bline in raw:
                parts=bline.decode("utf-8", "replace").rstrip("\n").split("|")
                if len(parts)<17: continue
                rxcui, lat, _, _, _, _, ispref, _, _, _, _, sab, tty, code, string, _, suppress = parts[:17]
                if lat != "ENG" or suppress not in {"", "N"}:
                    continue
                if sab != "RXNORM":
                    continue
                by_cui.setdefault(rxcui, []).append((string, tty, ispref, code))
        for rxcui, rows in by_cui.items():
            preferred=sorted(rows, key=lambda r: (r[2]!="Y", r[1] not in {"SCD","SBD","IN","BN"}))[0]
            display, tty, _, code=preferred
            strength=extract_strength(display)
            form=extract_form(display)
            generic=display if tty in {"IN","MIN","PIN"} else None
            brand=display if tty in {"BN","SBD","BPCK"} else None
            cur=con.execute(
                """INSERT OR IGNORE INTO medication_concepts
                   (source,source_id,display_name,normalized_name,tty,generic_name,brand_name,
                    strength,dosage_form,country)
                   VALUES('rxnorm',?,?,?,?,?,?,?,?,?)""",
                (rxcui,display,norm(display),tty,generic,brand,strength,form,"US/International terminology"),
            )
            concept=con.execute(
                "SELECT id FROM medication_concepts WHERE source='rxnorm' AND source_id=? ORDER BY id LIMIT 1",
                (rxcui,)
            ).fetchone()
            if not concept: continue
            cid=concept[0]
            inserted += int(cur.rowcount > 0)
            for string, rtty, _, _ in rows:
                c=con.execute(
                    "INSERT OR IGNORE INTO medication_aliases(concept_id,alias,normalized_alias,alias_type) VALUES(?,?,?,?)",
                    (cid,string,norm(string),rtty or "synonym")
                )
                aliases += int(c.rowcount > 0)
        con.commit()
    return {"concepts_inserted": inserted, "aliases_inserted": aliases, **stats()}

# This function downloads the configured RxNorm prescribable-content archive
# into the project data directory and then passes it to the normal RxNorm
# ingestion process.
def download_and_ingest_rxnorm(url: str | None = None) -> dict:
    url=url or settings.RXNORM_PRESCRIBABLE_URL
    dest=Path(settings.DATA_DIR)/"rxnorm_prescribable.zip"
    logger.info("Downloading RxNorm from %s", url)
    urllib.request.urlretrieve(url, dest)
    return ingest_rxnorm_zip(dest)

# This function imports optional DRAP medication data from a CSV file. Because
# exported column names can vary, it matches likely registration, product,
# ingredient, dosage-form, manufacturer and strength fields before storing each
# recognised medicine and its useful aliases in the local terminology index.
def ingest_drap_csv(csv_path: str | Path) -> dict:
    """Import a DRAP export/CSV using tolerant column-name matching.

    Expected information can include registration number, product/brand name,
    active ingredient/composition, dosage form, manufacturer/MAH and strength.
    """
    con=_connect()
    count=0
    with open(csv_path, newline="", encoding="utf-8-sig") as fh:
        reader=csv.DictReader(fh)
        for row in reader:
            low={norm(k).replace(" ","_"): (v or "").strip() for k,v in row.items()}
            def first(*keys):
                for k in keys:
                    for rk,rv in low.items():
                        if k in rk and rv: return rv
                return ""
            reg=first("registration_no","registration_number","registration")
            name=first("product_name","brand_name","brand","product")
            comp=first("composition","active_ingredient","ingredient")
            form=first("dosage_form","form")
            mfr=first("manufacturer","market_authorisation","market_authorization","mah")
            strength=first("strength") or extract_strength(name+" "+comp)
            if not name: continue
            source_id=reg or "drap-" + hashlib.sha256(f"{name}|{comp}|{mfr}".encode("utf-8")).hexdigest()[:20]
            cur=con.execute(
                """INSERT OR IGNORE INTO medication_concepts
                   (source,source_id,display_name,normalized_name,tty,generic_name,brand_name,
                    strength,dosage_form,active_ingredient,manufacturer,country)
                   VALUES('drap',?,?,?,?,?,?,?,?,?,?,?)""",
                (source_id,name,norm(name),"DRAP",comp or None,name,strength,form or None,comp or None,mfr or None,"Pakistan")
            )
            cidrow=con.execute(
                "SELECT id FROM medication_concepts WHERE source='drap' AND source_id=? ORDER BY id LIMIT 1",(source_id,)
            ).fetchone()
            if cidrow:
                cid=cidrow[0]
                for alias,atype in ((name,"brand"),(comp,"ingredient")):
                    if alias:
                        con.execute(
                            "INSERT OR IGNORE INTO medication_aliases(concept_id,alias,normalized_alias,alias_type) VALUES(?,?,?,?)",
                            (cid,alias,norm(alias),atype)
                        )
            count += int(cur.rowcount > 0)
        con.commit()
    return {"drap_inserted":count, **stats()}

# This function retrieves a limited pool of possible terminology matches before
# final ranking. Exact and prefix matches are checked first, followed by a
# restricted prefix search that can recover common spelling variations without
# scanning the entire medication database.
def _candidate_rows(
    query: str,
    limit: int = 500,
):
    """Retrieve a bounded candidate pool while tolerating misspellings.

    Exact and prefix matches are attempted first. A shorter four-character
    prefix is used for fuzzy recovery when needed; this allows spelling
    variation such as amoxycillin/amoxicillin without scanning the entire
    terminology database.
    """

    search_name = _canonical_query_name(
        query
    )

    if len(search_name) < 3:
        return []

    con = _connect()

    try:
        rows = con.execute(
            """
            SELECT
                c.*,
                a.alias,
                a.normalized_alias
            FROM medication_aliases a
            JOIN medication_concepts c
                ON c.id = a.concept_id
            WHERE
                a.normalized_alias = ?
                OR a.normalized_alias LIKE ?
                OR ? LIKE '%' || a.normalized_alias || '%'
            LIMIT ?
            """,
            (
                search_name,
                search_name + "%",
                search_name,
                limit,
            ),
        ).fetchall()

        tokens = [
            token
            for token in search_name.split()
            if len(token) >= 3
        ][:4]

        for token in tokens:

            # Four characters are normally restrictive enough while
            # still recovering common single-character spelling changes.
            prefix_length = min(
                4,
                len(token),
            )

            prefix = token[
                :prefix_length
            ]

            token_rows = con.execute(
                """
                SELECT
                    c.*,
                    a.alias,
                    a.normalized_alias
                FROM medication_aliases a
                JOIN medication_concepts c
                    ON c.id = a.concept_id
                WHERE
                    a.normalized_alias LIKE ?
                    OR a.normalized_alias LIKE ?
                LIMIT ?
                """,
                (
                    prefix + "%",
                    "% " + prefix + "%",
                    max(
                        60,
                        limit
                        // max(
                            1,
                            len(tokens),
                        ),
                    ),
                ),
            ).fetchall()

            rows += token_rows

        # Deduplicate aliases.
        seen = set()
        output = []

        for row in rows:

            key = (
                row["id"],
                row["normalized_alias"],
            )

            if key in seen:
                continue

            seen.add(
                key
            )

            output.append(
                dict(row)
            )

        return output[
            :limit
        ]

    finally:
        con.close()

# This function performs the final conservative medication matching step.
# It compares the cleaned query against candidate terminology aliases, applies
# stricter thresholds for uncertain single-word matches, checks compatibility
# with any supplied strength and dosage form, and ranks the best unique concepts.
# Only candidates meeting the configured confidence threshold are returned for
# later review rather than being treated as automatically confirmed medicines.
def suggest(
    query: str,
    top_k: int = 5,
) -> list[dict]:
    """Return conservative ranked medication terminology candidates."""

    nq = norm(
        query
    )

    if len(nq) < 3:
        return []

    q_strength = extract_strength(
        query
    )

    q_form = extract_form(
        query
    )

    name_only = _canonical_query_name(
        query
    )

    if len(name_only) < 3:
        return []

    name_tokens = (
        name_only.split()
    )

    single_name_token = (
        len(name_tokens) == 1
    )

    best = {}

    for row in _candidate_rows(
        query
    ):
        raw_alias = (
            row.get(
                "normalized_alias"
            )
            or row[
                "normalized_name"
            ]
        )

        alias_name = _clean_drug_name(
            raw_alias
        )

        if not alias_name:
            continue

        ratio = SequenceMatcher(
            None,
            name_only,
            alias_name,
        ).ratio()

       # Prefix boosting is only accepted when the match ends at a word boundary so
# ordinary words are not given a high medication score simply because they
# form the beginning of a longer drug name.

        boundary_match = (
            name_only == alias_name
            or alias_name.startswith(
                name_only + " "
            )
            or name_only.startswith(
                alias_name + " "
            )
        )

        if boundary_match:
            ratio = max(
                ratio,
                0.96,
            )

   # Single-word fuzzy matches use a stricter similarity threshold because short
# non-medication words are more likely to resemble a real medicine by chance.

        minimum_similarity = (
            settings
            .MEDICATION_CANDIDATE_THRESHOLD
        )

        if (
            single_name_token
            and not boundary_match
        ):
            minimum_similarity = max(
                minimum_similarity,
                0.84,
            )

        if ratio < minimum_similarity:
            continue



        row_strength = (
            row.get(
                "strength"
            )
        )

        row_form = (
            row.get(
                "dosage_form"
            )
        )

        strength_exact = bool(
            q_strength
            and row_strength
            and norm(q_strength)
            == norm(row_strength)
        )

        strength_compatible = (
            not q_strength
            or not row_strength
            or strength_exact
        )

        form_exact = bool(
            q_form
            and row_form
            and q_form
            in norm(row_form)
        )

        form_compatible = (
            not q_form
            or not row_form
            or form_exact
        )

        score = ratio
# Matching strength and dosage form slightly improve the ranking, while a
# conflicting known strength or form reduces it.

        # Prefer candidates that explicitly match the supplied strength.
        if q_strength:
            if strength_exact:
                score += 0.04
            elif row_strength:
                score -= 0.05

        # Prefer explicitly matching dosage forms.
        if q_form:
            if form_exact:
                score += 0.02
            elif row_form:
                score -= 0.02

        score = max(
            0.0,
            min(
                1.0,
                score,
            ),
        )

        concept_id = (
            row["id"]
        )

        item = {
            "concept_id":
                concept_id,

            "source":
                row["source"],

            "source_id":
                row["source_id"],

            "display_name":
                row["display_name"],

            "generic_name":
                row.get(
                    "generic_name"
                ),

            "brand_name":
                row.get(
                    "brand_name"
                ),

            "strength":
                row_strength,

            "dosage_form":
                row_form,

            "route":
                row.get(
                    "route"
                ),

            "manufacturer":
                row.get(
                    "manufacturer"
                ),

            "matched_via":
                row.get(
                    "alias"
                ),

            "score":
                round(
                    score,
                    3,
                ),

            "strength_compatible":
                strength_compatible,

            "strength_exact":
                strength_exact,

            "form_compatible":
                form_compatible,

            "form_exact":
                form_exact,
        }

        previous = best.get(
            concept_id
        )

        if (
            previous is None
            or (
                item["score"],
                item["strength_exact"],
                item["form_exact"],
            )
            >
            (
                previous["score"],
                previous[
                    "strength_exact"
                ],
                previous[
                    "form_exact"
                ],
            )
        ):
            best[
                concept_id
            ] = item

    output = sorted(
        best.values(),
        key=lambda item: (
            item["score"],
            item["strength_exact"],
            item["form_exact"],
        ),
        reverse=True,
    )

    return [
        item
        for item in output
        if (
            item["score"]
            >= settings
            .MEDICATION_CANDIDATE_THRESHOLD
        )
    ][:top_k]