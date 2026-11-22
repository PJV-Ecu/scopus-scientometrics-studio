"""
Step 2: Scopus API Client, Canonical Entity Resolution (Scopus AF-ID & ROR),
Asynchronous Job Engine, Text Analytics, and CSV/XLSX Exporters.
Uses only Python standard library modules for zero-dependency reliability.
"""

import csv
import io
import json
import os
import re
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
import zipfile
from collections import Counter
from datetime import datetime
from typing import Any, Optional
from xml.sax.saxutils import escape as xml_escape

from database import (
    detect_workspace_api_key,
    find_institution,
    format_afids,
    get_connection,
    normalize_afids,
    normalize_ror_id,
    normalize_text,
    upsert_institution,
)

SCOPUS_SEARCH_URL = "https://api.elsevier.com/content/search/scopus"
SCOPUS_AFFIL_SEARCH_URL = "https://api.elsevier.com/content/search/affiliation"
ROR_API_ORG_URL = "https://api.ror.org/v2/organizations"

# Active and completed background jobs
JOBS_LOCK = threading.Lock()
JOBS = {}

DEFAULT_STOPWORDS = {
    # English stopwords
    "the", "and", "of", "in", "to", "a", "for", "with", "on", "from", "by", "at", "an",
    "is", "are", "as", "into", "its", "between", "through", "under", "over", "after",
    "before", "during", "within", "without", "among", "against", "towards", "upon",
    "about", "above", "across", "along", "around", "behind", "below", "beneath", "beside",
    "beyond", "near", "off", "onto", "out", "outside", "past", "since", "throughout",
    "toward", "until", "up", "via", "using", "based", "study", "analysis", "case",
    "effects", "effect", "new", "two", "three", "first", "their", "that", "this", "these",
    "those", "which", "who", "whom", "whose", "where", "when", "why", "how", "all", "any",
    "both", "each", "few", "more", "most", "other", "some", "such", "no", "nor", "not",
    "only", "own", "same", "so", "than", "too", "very", "can", "will", "just", "should",
    "now", "also", "been", "being", "have", "has", "had", "having", "do", "does", "did",
    "doing", "would", "could", "might", "must", "shall", "may",
    # Spanish / Portuguese stopwords
    "de", "la", "el", "en", "y", "del", "los", "las", "un", "una", "para", "con", "por",
    "al", "como", "mas", "más", "pero", "sus", "le", "ya", "o", "este", "sí", "porque",
    "esta", "entre", "cuando", "muy", "sin", "sobre", "también", "me", "hasta", "hay",
    "donde", "quien", "desde", "todo", "nos", "durante", "todos", "uno", "les", "ni",
    "contra", "otros", "ese", "eso", "ante", "ellos", "e", "esto", "mí", "antes",
    "algunos", "qué", "unos", "yo", "otro", "otras", "otra", "él", "tanto", "esa",
    "estos", "mucho", "quienes", "nada", "muchos", "cual", "poco", "ella", "estar",
    "estas", "algunas", "algo", "nosotros", "mi", "mis", "tú", "te", "ti", "tu", "tus",
    "ellas", "nosotras", "vosotros", "vosotras", "os", "mío", "mía", "míos", "mías",
    "em", "da", "do", "dos", "das", "na", "no", "nas", "nos", "um", "uma",
}

AFFIL_TOKEN_STOPWORDS = {
    "de", "del", "la", "las", "los", "el", "en", "y", "e", "of", "the", "for", "and",
    "in", "at", "ecuador", "sede", "campus", "matriz", "particular",
}

EN_TO_ES_INST_TOKENS = {
    "university": "universidad",
    "polytechnic": "politecnica",
    "school": "escuela",
    "higher": "superior",
    "national": "nacional",
    "catholic": "catolica",
    "pontifical": "pontificia",
    "central": "central",
    "state": "estatal",
    "technical": "tecnica",
    "technological": "tecnologica",
    "institute": "instituto",
    "public": "publico",
    "research": "investigacion",
    "biodiversity": "biodiversidad",
    "health": "salud",
    "salesian": "salesiana",
    "coastal": "litoral",
    "amazon": "amazonica",
    "cultural": "cultural",
    "heritage": "patrimonio",
    "fisheries": "pesca",
    "aquaculture": "acuicultura",
    "agricultural": "agropecuarias",
    "sciences": "ciencias",
    "social": "sociales",
    "education": "educacion",
}


def get_settings() -> dict:
    conn = get_connection()
    rows = conn.execute("SELECT key, value FROM settings").fetchall()
    conn.close()
    settings = {r["key"]: r["value"] for r in rows}
    if not settings.get("api_key"):
        env_key = (
            os.environ.get("SCOPUS_API_KEY")
            or os.environ.get("Elsevier_API")
            or detect_workspace_api_key()
            or ""
        )
        if env_key.strip():
            settings["api_key"] = env_key.strip()
    return settings


def format_entity_identifier_badge(entity: dict) -> str:
    """Return a concise identifier string for logs and titles (e.g. 'AF-ID:60104441 | ROR:0198j4566')."""
    parts = []
    afids = normalize_afids(entity.get("afid", ""))
    if afids:
        parts.append(f"AF-ID:{','.join(afids)}")
    if entity.get("ror_id"):
        parts.append(f"ROR:{entity['ror_id']}")
    if not parts and entity.get("entity_uid"):
        parts.append(entity["entity_uid"])
    return " | ".join(parts)


def _canonical_inst_tokens(label: str, acronym: str = "") -> set[str]:
    norm = normalize_text(label)
    if not norm:
        return set()
    acr_norm = normalize_text(acronym)
    raw_tokens = norm.split()
    mapped = []
    for t in raw_tokens:
        if t in AFFIL_TOKEN_STOPWORDS:
            continue
        if acr_norm and t == acr_norm and len(raw_tokens) >= 3:
            continue
        mapped.append(EN_TO_ES_INST_TOKENS.get(t, t))
    return set(mapped)


def _entity_candidate_names(entity: dict) -> list[str]:
    names = []
    primary = (entity.get("name") or "").strip()
    if primary and not primary.startswith("Entidad "):
        names.append(primary)
    for raw_alias in (entity.get("aliases") or "").split(";"):
        a = raw_alias.strip()
        if len(a) >= 6 and normalize_ror_id(a) == "" and not a.upper().startswith("ROR:"):
            if a not in names:
                names.append(a)
    return names


def _build_ror_fallback_clause(entity: dict, default_country: str = "Ecuador") -> str:
    """
    Translate a canonical ROR-defined entity without a 60xxxxxx Scopus profile
    into a disambiguated Scopus affiliation boolean expression.
    """
    candidates = _entity_candidate_names(entity)
    distinct_forms = []
    seen_norms = set()
    for cand in candidates:
        clean = cand.replace('"', "").strip()
        n = normalize_text(clean)
        if clean and n and n not in seen_norms:
            seen_norms.add(n)
            distinct_forms.append(clean)
        if len(distinct_forms) >= 3:
            break

    if not distinct_forms:
        fallback_lbl = (entity.get("acronym") or entity.get("name") or "").replace('"', "").strip()
        distinct_forms = [fallback_lbl] if fallback_lbl else []

    if len(distinct_forms) == 1:
        name_expr = f'AFFIL("{distinct_forms[0]}")'
    else:
        name_expr = "(" + " OR ".join(f'AFFIL("{nm}")' for nm in distinct_forms) + ")"

    subclauses = [name_expr]
    dcity = (entity.get("disambig_city") or "").replace('"', "").strip()
    if dcity:
        subclauses.append(f'AFFIL("{dcity}")')

    country = (entity.get("country") or default_country or "").replace('"', "").strip()
    if country:
        subclauses.append(f"AFFILCOUNTRY({country})")

    return "(" + " AND ".join(subclauses) + ")" if len(subclauses) > 1 else subclauses[0]


def build_scopus_query(
    entity_ref: Any = None,
    year: str = "2025",
    subj_area: str = "ALL",
    open_access_only: bool = False,
    afid: str = "",
    ror_id: str = "",
    extra_filter: str = "",
    country_filter: str = "Ecuador",
    institution_name: str = "",
) -> str:
    """
    Build a canonical Scopus boolean search query defined by Scopus AF-ID or ROR ID.
    - Whenever one or more Scopus AF-IDs exist, emits pure `AF-ID(...)` with zero institution names.
    - When defined by ROR ID (unprofiled/pending in Scopus), resolves the ROR record's canonical
      disambiguated clause.
    """
    explicit_afids = normalize_afids(afid)
    explicit_ror = normalize_ror_id(ror_id)

    if not explicit_afids and isinstance(entity_ref, str):
        explicit_afids = normalize_afids(entity_ref)
    if not explicit_ror and isinstance(entity_ref, str):
        explicit_ror = normalize_ror_id(entity_ref)

    entity = None
    if isinstance(entity_ref, dict):
        entity = entity_ref
    else:
        lookup_target = entity_ref or explicit_afids or explicit_ror or institution_name
        if lookup_target:
            conn = get_connection()
            try:
                if isinstance(lookup_target, list):
                    for item in lookup_target:
                        entity = find_institution(conn, item)
                        if entity:
                            break
                else:
                    entity = find_institution(conn, lookup_target)
            finally:
                conn.close()

    resolved_afids = explicit_afids or (normalize_afids(entity.get("afid", "")) if entity else [])

    if resolved_afids:
        if len(resolved_afids) == 1:
            aff_clause = f"AF-ID({resolved_afids[0]})"
        else:
            aff_clause = "(" + " OR ".join(f"AF-ID({fid})" for fid in resolved_afids) + ")"
    elif entity:
        aff_clause = _build_ror_fallback_clause(entity, default_country=country_filter)
    elif explicit_ror:
        # Resolve live ROR metadata if external ROR ID is not yet in local directory
        try:
            ror_meta = fetch_ror_metadata(explicit_ror)
            aff_clause = _build_ror_fallback_clause(ror_meta, default_country=ror_meta.get("country", country_filter))
        except Exception:
            aff_clause = f'AFFIL("{explicit_ror}")'
    else:
        raw_str = str(entity_ref or institution_name or "").replace('"', "").strip()
        aff_clause = f'AFFIL("{raw_str}")'
        if country_filter and country_filter.strip():
            aff_clause = f"({aff_clause} AND AFFILCOUNTRY({country_filter.strip()}))"

    clauses = [aff_clause]

    if subj_area and subj_area.upper().strip() != "ALL":
        clauses.append(f"SUBJAREA({subj_area.upper().strip()})")

    if year and str(year).strip().upper() != "ALL":
        y_str = str(year).strip()
        if "-" in y_str:
            parts = [p.strip() for p in y_str.split("-") if p.strip().isdigit()]
            if len(parts) == 2:
                y1, y2 = int(parts[0]), int(parts[1])
                clauses.append(f"PUBYEAR > {y1 - 1} AND PUBYEAR < {y2 + 1}")
            else:
                clauses.append(f"PUBYEAR = {y_str}")
        else:
            clauses.append(f"PUBYEAR = {y_str}")

    if open_access_only:
        clauses.append("ACCESSTYPE(OA)")

    if extra_filter and extra_filter.strip():
        clauses.append(f"({extra_filter.strip()})")

    return " AND ".join(clauses)


def scopus_api_request(
    query: str,
    api_key: str,
    inst_token: str = "",
    view: str = "STANDARD",
    count: int = 25,
    start: int = 0,
    max_retries: int = 3,
    endpoint_url: str = SCOPUS_SEARCH_URL,
) -> dict:
    """
    Execute a single Elsevier Scopus API call with retry on transient errors (429/5xx)
    and automatic fallback from COMPLETE to STANDARD view if unauthorized.
    """
    if not api_key or not api_key.strip():
        raise ValueError("Scopus API key is not configured. Please add your API key in Settings.")

    params = {
        "query": query,
        "count": str(count),
        "start": str(start),
    }
    if endpoint_url == SCOPUS_SEARCH_URL:
        params["view"] = view

    url = f"{endpoint_url}?{urllib.parse.urlencode(params)}"
    headers = {
        "X-ELS-APIKey": api_key.strip(),
        "Accept": "application/json",
        "User-Agent": "ScopusProductivityStudio/2.1",
    }
    if inst_token and inst_token.strip():
        headers["X-ELS-Insttoken"] = inst_token.strip()

    attempt = 0
    while attempt < max_retries:
        attempt += 1
        req = urllib.request.Request(url, headers=headers, method="GET")
        try:
            with urllib.request.urlopen(req, timeout=25) as resp:
                raw = resp.read().decode("utf-8", errors="replace")
                return json.loads(raw)
        except urllib.error.HTTPError as e:
            err_body = ""
            try:
                err_body = e.read().decode("utf-8", errors="replace")
            except Exception:
                pass

            if (
                endpoint_url == SCOPUS_SEARCH_URL
                and e.code in (401, 403)
                and view.upper() == "COMPLETE"
            ):
                return scopus_api_request(
                    query=query,
                    api_key=api_key,
                    inst_token=inst_token,
                    view="STANDARD",
                    count=count,
                    start=start,
                    max_retries=max_retries,
                    endpoint_url=endpoint_url,
                )

            if e.code in (429, 500, 502, 503, 504) and attempt < max_retries:
                time.sleep(3 * attempt)
                continue

            raise RuntimeError(f"Scopus API HTTP {e.code}: {err_body[:240] or e.reason}") from e
        except urllib.error.URLError as e:
            if attempt < max_retries:
                time.sleep(2 * attempt)
                continue
            raise RuntimeError(f"Network connection error reaching api.elsevier.com: {e.reason}") from e


def fetch_ror_metadata(ror_id: str) -> dict:
    """Resolve official institutional metadata directly from ROR API v2 using a ROR ID."""
    rid = normalize_ror_id(ror_id)
    if not rid:
        raise ValueError(f"Identificador ROR inválido: '{ror_id}'. Formato esperado: 0xxxxxxxx.")

    url = f"{ROR_API_ORG_URL}/{rid}"
    req = urllib.request.Request(
        url,
        headers={
            "Accept": "application/json",
            "User-Agent": "ScopusProductivityStudio/2.1",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read().decode("utf-8", errors="replace"))
    except urllib.error.HTTPError as e:
        if e.code == 404:
            raise ValueError(f"No se encontró ninguna organización en ror.org para ROR:{rid}.") from e
        raise RuntimeError(f"Error consultando ROR API ({e.code}): {e.reason}") from e
    except urllib.error.URLError as e:
        raise RuntimeError(f"No se pudo conectar a api.ror.org: {e.reason}") from e

    names_arr = data.get("names", [])
    es_label = ""
    ror_display = ""
    acronyms = []
    variants = []

    for n in names_arr:
        val = str(n.get("value", "")).strip()
        if not val:
            continue
        ntypes = n.get("types", [])
        if "acronym" in ntypes:
            if val not in acronyms:
                acronyms.append(val)
        else:
            if val not in variants:
                variants.append(val)
        if "ror_display" in ntypes:
            ror_display = val
        if n.get("lang") == "es" and "label" in ntypes and not es_label:
            es_label = val

    locs = data.get("locations", [])
    city = ""
    country = "Ecuador"
    if locs:
        gd = locs[0].get("geonames_details", {})
        city = str(gd.get("name", "")).strip()
        country = str(gd.get("country_name", "") or "Ecuador").strip()

    rtypes = [str(t).lower() for t in data.get("types", [])]
    category = "University" if "education" in rtypes else "Research Institute"
    if "government" in rtypes:
        inst_type = "Public"
    elif "nonprofit" in rtypes or "company" in rtypes or "private" in rtypes:
        inst_type = "Private"
    else:
        inst_type = "Public"

    return {
        "ror_id": rid,
        "name": es_label or ror_display or (variants[0] if variants else f"ROR:{rid}"),
        "acronym": acronyms[0] if acronyms else "",
        "city": city,
        "country": country,
        "category": category,
        "inst_type": inst_type,
        "aliases": "; ".join(variants[:6]),
    }


def fetch_scopus_affiliation_metadata(afid: str, api_key: str, inst_token: str = "") -> dict:
    """Resolve institutional metadata from Elsevier Scopus using a numeric Scopus AF-ID."""
    afids = normalize_afids(afid)
    if not afids:
        raise ValueError(f"Scopus AF-ID inválido: '{afid}'. Se esperaba un código numérico de 8 a 10 dígitos.")
    primary_afid = afids[0]

    if not api_key or not api_key.strip():
        return {"afid": format_afids(afids)}

    # 1. Try Elsevier Affiliation Search API
    try:
        resp = scopus_api_request(
            query=f"AF-ID({primary_afid})",
            api_key=api_key,
            inst_token=inst_token,
            count=1,
            endpoint_url=SCOPUS_AFFIL_SEARCH_URL,
        )
        entries = resp.get("search-results", {}).get("entry", [])
        if isinstance(entries, dict):
            entries = [entries]
        for ent in entries:
            aname = str(ent.get("affiliation-name", "")).strip()
            if aname and "Result set was empty" not in aname:
                variants = []
                raw_vars = ent.get("name-variant", [])
                if isinstance(raw_vars, dict):
                    raw_vars = [raw_vars]
                for rv in raw_vars:
                    vtxt = str(rv.get("$", "") if isinstance(rv, dict) else rv).strip()
                    if vtxt and vtxt not in variants:
                        variants.append(vtxt)
                return {
                    "afid": format_afids(afids),
                    "name": aname,
                    "city": str(ent.get("city", "") or "").strip(),
                    "country": str(ent.get("country", "") or "Ecuador").strip(),
                    "aliases": "; ".join(variants[:6]),
                }
    except Exception:
        pass

    # 2. Fallback to standard Scopus Search API inspection
    resp = scopus_api_request(
        query=f"AF-ID({primary_afid})",
        api_key=api_key,
        inst_token=inst_token,
        view="STANDARD",
        count=5,
    )
    entries = resp.get("search-results", {}).get("entry", [])
    if isinstance(entries, dict):
        entries = [entries]
    for ent in entries:
        affs = ent.get("affiliation", [])
        if isinstance(affs, dict):
            affs = [affs]
        for a in affs:
            if isinstance(a, dict) and str(a.get("afid", "")).strip() == primary_afid:
                return {
                    "afid": format_afids(afids),
                    "name": str(a.get("affilname", "")).strip(),
                    "city": str(a.get("affiliation-city", "") or "").strip(),
                    "country": str(a.get("affiliation-country", "") or "Ecuador").strip(),
                }

    return {"afid": format_afids(afids)}


def _jaccard(a: set[str], b: set[str]) -> float:
    if not a or not b:
        return 0.0
    return len(a & b) / float(len(a | b))


def _best_token_similarity(test_names: list[str], entity: dict) -> float:
    acr = entity.get("acronym", "")
    cand_sets = [
        _canonical_inst_tokens(nm, acr)
        for nm in _entity_candidate_names(entity)
    ]
    cand_sets = [s for s in cand_sets if len(s) >= 2]
    if not cand_sets:
        return 0.0

    best = 0.0
    for tn in test_names:
        tset = _canonical_inst_tokens(tn, acr)
        if len(tset) < 2:
            continue
        for cset in cand_sets:
            score = _jaccard(tset, cset)
            if score > best:
                best = score
    return best


def _affiliation_matches_entity(
    aff_name: str,
    variants: list[str],
    aff_city: str,
    aff_country: str,
    entity: dict,
    all_entities: list[dict],
) -> bool:
    """
    Strictly verify that a candidate Scopus Affiliation profile belongs to `entity`
    and does not collide with any other institution in `all_entities`.
    """
    expected_country = normalize_text(entity.get("country") or "Ecuador")
    if aff_country and expected_country and normalize_text(aff_country) != expected_country:
        return False

    dcity = normalize_text(entity.get("disambig_city") or "")
    if dcity:
        city_blob = f"{normalize_text(aff_city)} {normalize_text(aff_name)}"
        if dcity not in city_blob:
            return False

    test_names = [x for x in [aff_name] + list(variants) if x and x.strip()]
    target_score = _best_token_similarity(test_names, entity)
    if target_score < 0.80:
        return False

    # Ensure no other distinct entity in the national directory has a higher similarity
    target_uid = entity.get("entity_uid")
    for other in all_entities:
        if other.get("entity_uid") == target_uid:
            continue
        other_score = _best_token_similarity([aff_name], other)
        if other_score > target_score:
            return False

    return True


def ensure_entity_scopus_afid(
    entity: dict,
    api_key: str,
    inst_token: str = "",
    force: bool = False,
) -> tuple[list[str], str]:
    """
    Ensure an institutional entity has its curated 8-digit `60xxxxxx` Scopus AF-ID
    cached in SQLite if one exists in Elsevier's index.
    Returns `(afids_list, resolution_status)`.
    """
    existing_afids = normalize_afids(entity.get("afid", ""))
    if existing_afids and not force:
        return existing_afids, "cached"

    if entity.get("afid_status") == "unprofiled" and not force:
        return [], "unprofiled"

    if not api_key or not api_key.strip():
        return existing_afids, "no_api_key"

    conn = get_connection()
    all_entities = [dict(r) for r in conn.execute("SELECT * FROM institutions").fetchall()]
    conn.close()

    discovered_afids: list[str] = []
    country = (entity.get("country") or "Ecuador").strip()
    cand_names = _entity_candidate_names(entity)[:3]

    # Step 1: Try Elsevier Affiliation Search API (/content/search/affiliation)
    aff_endpoint_allowed = True
    for cname in cand_names:
        if not aff_endpoint_allowed:
            break
        clean_nm = cname.replace('"', "").strip()
        aff_q = f'affil("{clean_nm}")'
        if country:
            aff_q += f" AND affilcountry({country})"
        try:
            resp = scopus_api_request(
                query=aff_q,
                api_key=api_key,
                inst_token=inst_token,
                count=10,
                endpoint_url=SCOPUS_AFFIL_SEARCH_URL,
            )
            entries = resp.get("search-results", {}).get("entry", [])
            if isinstance(entries, dict):
                entries = [entries]
            for ent in entries:
                raw_id = str(ent.get("dc:identifier", "") or ent.get("eid", ""))
                fids = [x for x in normalize_afids(raw_id) if len(x) == 8 and x.startswith("60")]
                if not fids:
                    continue
                aname = str(ent.get("affiliation-name", "")).strip()
                acity = str(ent.get("city", "") or "").strip()
                acountry = str(ent.get("country", "") or "").strip()
                raw_vars = ent.get("name-variant", [])
                if isinstance(raw_vars, dict):
                    raw_vars = [raw_vars]
                vars_list = [
                    str(v.get("$", "") if isinstance(v, dict) else v).strip()
                    for v in raw_vars
                ]
                if _affiliation_matches_entity(aname, vars_list, acity, acountry, entity, all_entities):
                    for fid in fids:
                        if fid not in discovered_afids:
                            discovered_afids.append(fid)
        except Exception as exc:
            msg = str(exc)
            if "HTTP 401" in msg or "HTTP 403" in msg:
                aff_endpoint_allowed = False
            continue

    # Step 2: Fallback to inspecting `entry[].affiliation[]` from /content/search/scopus
    if not discovered_afids:
        fallback_q = _build_ror_fallback_clause(entity, default_country=country)
        try:
            resp = scopus_api_request(
                query=fallback_q,
                api_key=api_key,
                inst_token=inst_token,
                view="STANDARD",
                count=15,
                start=0,
            )
            entries = resp.get("search-results", {}).get("entry", [])
            if isinstance(entries, dict):
                entries = [entries]
            afid_hits = Counter()
            for ent in entries:
                affs = ent.get("affiliation", [])
                if isinstance(affs, dict):
                    affs = [affs]
                for a in affs:
                    if not isinstance(a, dict):
                        continue
                    fid = str(a.get("afid", "")).strip()
                    if not (len(fid) == 8 and fid.startswith("60")):
                        continue
                    aname = str(a.get("affilname", "")).strip()
                    acity = str(a.get("affiliation-city", "") or "").strip()
                    acountry = str(a.get("affiliation-country", "") or "").strip()
                    if _affiliation_matches_entity(aname, [], acity, acountry, entity, all_entities):
                        afid_hits[fid] += 1
            for fid, _cnt in afid_hits.most_common():
                if fid not in discovered_afids:
                    discovered_afids.append(fid)
        except Exception:
            pass

    # Persist resolution state into SQLite if entity is in directory
    if entity.get("id"):
        conn = get_connection()
        try:
            if discovered_afids:
                merged = format_afids(existing_afids + discovered_afids)
                upsert_institution(
                    conn,
                    {
                        "id": entity["id"],
                        "ror_id": entity.get("ror_id", ""),
                        "afid": merged,
                        "afid_status": "verified",
                    },
                    allow_provisional=True,
                )
                entity["afid"] = merged
                entity["afid_status"] = "verified"
            else:
                conn.execute(
                    "UPDATE institutions SET afid_status = 'unprofiled' WHERE id = ?",
                    (entity["id"],),
                )
                conn.commit()
                entity["afid_status"] = "unprofiled"
        finally:
            conn.close()

    return (discovered_afids, "discovered") if discovered_afids else ([], "unprofiled")


def resolve_entity_metadata(
    ror_id: str = "",
    afid: str = "",
    api_key: str = "",
    inst_token: str = "",
) -> dict:
    """
    Resolve complete entity metadata from a ROR ID and/or Scopus AF-ID so users can
    define entities purely by identifier without typing names.
    """
    rid = normalize_ror_id(ror_id)
    afids = normalize_afids(afid)
    if not rid and not afids:
        raise ValueError("Ingresa un Scopus AF-ID o un ROR ID válido para resolver la entidad.")

    result: dict[str, Any] = {
        "ror_id": rid,
        "afid": format_afids(afids),
        "acronym": "",
        "name": "",
        "category": "University",
        "inst_type": "Public",
        "city": "",
        "country": "Ecuador",
        "aliases": "",
    }

    if rid:
        ror_meta = fetch_ror_metadata(rid)
        result.update({k: v for k, v in ror_meta.items() if v})

    if afids and api_key:
        scopus_meta = fetch_scopus_affiliation_metadata(afids[0], api_key=api_key, inst_token=inst_token)
        if not result["name"] and scopus_meta.get("name"):
            result["name"] = scopus_meta["name"]
        if not result["city"] and scopus_meta.get("city"):
            result["city"] = scopus_meta["city"]
        if scopus_meta.get("country"):
            result["country"] = scopus_meta["country"]
        if scopus_meta.get("aliases"):
            merged_aliases = "; ".join(
                dict.fromkeys(
                    [x.strip() for x in f"{result['aliases']}; {scopus_meta['aliases']}".split(";") if x.strip()]
                )
            )
            result["aliases"] = merged_aliases

    # If ROR was provided without AF-ID and API key is active, attempt automatic AF-ID discovery
    if rid and not afids and api_key and result.get("name"):
        found_afids, _ = ensure_entity_scopus_afid(result, api_key=api_key, inst_token=inst_token, force=True)
        if found_afids:
            result["afid"] = format_afids(found_afids)

    return result


def parse_scopus_entry(
    entry: dict,
    target_afids: Optional[set[str]] = None,
    target_pattern: str = "",
) -> dict:
    """
    Extract normalized publication fields from a single Scopus entry object.
    Isolates institutional authors primarily via canonical Scopus `AF-ID` matching.
    """
    def get_val(field: str) -> str:
        v = entry.get(field)
        if v is None:
            return ""
        if isinstance(v, list):
            if len(v) == 1 and isinstance(v[0], dict) and "$" in v[0]:
                return str(v[0]["$"])
            return "; ".join(str(x.get("$", x) if isinstance(x, dict) else x) for x in v)
        if isinstance(v, dict):
            return str(v.get("$", ""))
        return str(v).strip()

    title = get_val("dc:title")
    if not title or "Result set was empty" in title:
        return {}

    journal = get_val("prism:publicationName")
    pub_date = get_val("prism:coverDate")
    issn = get_val("prism:issn")
    eissn = get_val("prism:eIssn")
    isbn = get_val("prism:isbn")
    id_number = issn or eissn or isbn
    doi = get_val("prism:doi")
    agg_type = get_val("prism:aggregationType") or "Journal"
    cited_by_str = get_val("citedby-count")
    cited_by = int(cited_by_str) if cited_by_str.isdigit() else 0

    aff_raw = entry.get("affiliation", [])
    if isinstance(aff_raw, dict):
        aff_raw = [aff_raw]
    aff_names = []
    matched_entry_afids = set(target_afids or set())

    for a in aff_raw:
        if isinstance(a, dict):
            aname = str(a.get("affilname", "")).strip()
            afid = str(a.get("afid", "")).strip()
            if aname:
                tag = f"{aname} [AF-ID:{afid}]" if afid else aname
                if tag not in aff_names:
                    aff_names.append(tag)
            if not matched_entry_afids and target_pattern and aname:
                if re.search(target_pattern, aname, re.IGNORECASE) and afid:
                    matched_entry_afids.add(afid)

    affiliations_str = "; ".join(aff_names)

    auth_raw = entry.get("author", [])
    if isinstance(auth_raw, dict):
        auth_raw = [auth_raw]
    all_authors = []
    target_authors = []
    for auth in auth_raw:
        if isinstance(auth, dict):
            aname = auth.get("authname")
            if not aname:
                given = auth.get("given-name", "")
                surname = auth.get("surname", "")
                initials = auth.get("initials", "")
                aname = f"{given} {surname}".strip() if given else f"{surname} {initials}".strip()
            aname = str(aname or "").strip()
            if aname and aname not in all_authors:
                all_authors.append(aname)

            if matched_entry_afids:
                afid_field = auth.get("afid", [])
                if isinstance(afid_field, dict):
                    afid_field = [afid_field]
                auth_afids = set()
                for af in afid_field:
                    if isinstance(af, dict):
                        auth_afids.add(str(af.get("$", "")).strip())
                    else:
                        auth_afids.add(str(af).strip())
                if auth_afids.intersection(matched_entry_afids) and aname not in target_authors:
                    target_authors.append(aname)

    if not all_authors:
        creator = get_val("dc:creator")
        if creator:
            all_authors.append(creator)

    authors_list_str = "; ".join(all_authors)
    if target_authors:
        target_authors_str = "; ".join(target_authors)
    elif matched_entry_afids and any(f"AF-ID:{fid}" in affiliations_str for fid in matched_entry_afids):
        target_authors_str = authors_list_str
    elif target_pattern and re.search(target_pattern, affiliations_str, re.IGNORECASE):
        target_authors_str = authors_list_str
    else:
        target_authors_str = ""

    sa_raw = entry.get("subject-area", [])
    if isinstance(sa_raw, dict):
        sa_raw = [sa_raw]
    sa_list = []
    for sa in sa_raw:
        if isinstance(sa, dict) and "$" in sa:
            sa_list.append(str(sa["$"]).strip())
    if sa_list:
        main_area = sa_list[0]
        specific_areas = "; ".join(sa_list)
    else:
        main_area = agg_type
        specific_areas = ""

    return {
        "article_name": title,
        "journal_name": journal,
        "date_publication": pub_date,
        "issn_isbn": id_number,
        "main_knowledge_area": main_area,
        "specific_areas": specific_areas,
        "target_authors": target_authors_str,
        "authors_list": authors_list_str,
        "affiliations": affiliations_str,
        "doi": doi,
        "cited_by": cited_by,
    }


def start_afid_sync_job(payload: dict) -> str:
    """Background job to discover and verify 60xxxxxx Scopus AF-IDs for directory entities."""
    job_id = str(uuid.uuid4())[:8]
    force = bool(payload.get("force", False))

    conn = get_connection()
    if force:
        targets = [dict(r) for r in conn.execute("SELECT * FROM institutions WHERE active = 1 ORDER BY id").fetchall()]
    else:
        targets = [
            dict(r)
            for r in conn.execute(
                "SELECT * FROM institutions WHERE active = 1 AND (afid IS NULL OR afid = '') ORDER BY id"
            ).fetchall()
        ]
    conn.close()

    job_state = {
        "id": job_id,
        "type": "sync_afids",
        "status": "running",
        "title": "Sincronización de Scopus AF-IDs",
        "current": 0,
        "total": max(1, len(targets)),
        "percent": 0,
        "message": "Iniciando resolución de identificadores Scopus AF-ID...",
        "logs": [],
        "cancelled": False,
        "started_at": datetime.now().strftime("%H:%M:%S"),
    }
    with JOBS_LOCK:
        JOBS[job_id] = job_state

    def _worker():
        settings = get_settings()
        api_key = payload.get("api_key") or settings.get("api_key", "")
        inst_token = settings.get("inst_token", "")
        sleep_time = float(payload.get("sleep_time", 0.35) or 0.35)

        if not api_key:
            with JOBS_LOCK:
                JOBS[job_id]["status"] = "error"
                JOBS[job_id]["message"] = "Configura primero tu Scopus API Key en esta pestaña."
            return

        discovered_count = 0
        for idx, ent in enumerate(targets):
            with JOBS_LOCK:
                if JOBS[job_id]["cancelled"]:
                    JOBS[job_id]["status"] = "cancelled"
                    JOBS[job_id]["message"] = "Sincronización cancelada por el usuario."
                    return
                JOBS[job_id]["current"] = idx + 1
                JOBS[job_id]["percent"] = int(round((idx / max(1, len(targets))) * 100))
                id_tag = ent.get("ror_id") or ent.get("entity_uid")
                JOBS[job_id]["message"] = f"Resolviendo ({idx + 1}/{len(targets)}): [{ent['acronym']}] {id_tag}"

            afids, status = ensure_entity_scopus_afid(ent, api_key=api_key, inst_token=inst_token, force=force)
            if afids:
                discovered_count += 1
                log_line = f"✓ [{ent['acronym']}] ROR:{ent.get('ror_id') or '—'} → AF-ID({', '.join(afids)})"
            else:
                log_line = f"• [{ent['acronym']}] ROR:{ent.get('ror_id') or '—'} → sin perfil 60xxxxxx en Scopus ({status})"
            with JOBS_LOCK:
                JOBS[job_id]["logs"].append(log_line)

            if idx < len(targets) - 1 and sleep_time > 0:
                time.sleep(min(sleep_time, 2.0))

        with JOBS_LOCK:
            JOBS[job_id]["percent"] = 100
            JOBS[job_id]["status"] = "completed"
            JOBS[job_id]["message"] = (
                f"Sincronización completada: {discovered_count}/{len(targets)} perfiles Scopus AF-ID vinculados."
            )

    t = threading.Thread(target=_worker, daemon=True)
    t.start()
    return job_id


def start_comparison_job(payload: dict) -> str:
    """
    Launch a background job to query Scopus total publication counts across a list of
    entities defined by canonical identifiers (`entity_uid`, `afid`, or `ror_id`).
    """
    job_id = str(uuid.uuid4())[:8]
    entity_refs = payload.get("entity_ids") or payload.get("institutions") or []
    year = str(payload.get("year", "2025")).strip()
    subj_area = str(payload.get("subj_area", "ALL")).strip()
    open_access_only = bool(payload.get("open_access_only", False))
    title = payload.get("title") or f"Comparativa Institucional Scopus ({year} - {subj_area})"
    subtitle = payload.get("subtitle") or f"Área: {subj_area} | Año: {year}"
    reference_line = float(payload.get("reference_line", 0) or 0)
    category_filter = payload.get("category_filter", "Custom")

    job_state = {
        "id": job_id,
        "type": "comparison",
        "status": "running",
        "title": title,
        "current": 0,
        "total": len(entity_refs),
        "percent": 0,
        "message": "Iniciando consultas a Scopus por identificador (AF-ID / ROR)...",
        "logs": [],
        "result_run_id": None,
        "cancelled": False,
        "started_at": datetime.now().strftime("%H:%M:%S"),
    }
    with JOBS_LOCK:
        JOBS[job_id] = job_state

    def _worker():
        settings = get_settings()
        api_key = payload.get("api_key") or settings.get("api_key", "")
        inst_token = settings.get("inst_token", "")
        sleep_time = float(payload.get("sleep_time", settings.get("sleep_time", 0.5)) or 0.5)

        results = []
        for idx, raw_ref in enumerate(entity_refs):
            conn = get_connection()
            entity = find_institution(conn, raw_ref)
            conn.close()

            if not entity:
                # Allow ad-hoc identifier (AF-ID or ROR ID) not yet in directory
                try:
                    resolved = resolve_entity_metadata(
                        ror_id=normalize_ror_id(raw_ref),
                        afid=format_afids(raw_ref),
                        api_key=api_key,
                        inst_token=inst_token,
                    )
                    conn = get_connection()
                    entity = upsert_institution(conn, resolved, allow_provisional=True)
                    conn.close()
                except Exception:
                    entity = {
                        "entity_uid": str(raw_ref),
                        "ror_id": normalize_ror_id(raw_ref),
                        "afid": format_afids(raw_ref),
                        "afid_status": "verified" if normalize_afids(raw_ref) else "unprofiled",
                        "acronym": "",
                        "name": str(raw_ref),
                        "category": "University",
                        "inst_type": "Public",
                        "city": "",
                        "country": "Ecuador",
                        "aliases": "",
                    }

            # Automatically discover & cache 60xxxxxx Scopus AF-ID on first live query
            if not normalize_afids(entity.get("afid", "")) and entity.get("afid_status") == "pending":
                ensure_entity_scopus_afid(entity, api_key=api_key, inst_token=inst_token)

            id_badge = format_entity_identifier_badge(entity)
            label_tag = f"[{entity['acronym']}] {id_badge}" if entity.get("acronym") else id_badge

            with JOBS_LOCK:
                if JOBS[job_id]["cancelled"]:
                    JOBS[job_id]["status"] = "cancelled"
                    JOBS[job_id]["message"] = "Consulta cancelada por el usuario."
                    return
                JOBS[job_id]["current"] = idx + 1
                JOBS[job_id]["percent"] = int(round((idx / max(1, len(entity_refs))) * 100))
                JOBS[job_id]["message"] = f"Consultando ({idx + 1}/{len(entity_refs)}): {label_tag}"

            query = build_scopus_query(
                entity_ref=entity,
                year=year,
                subj_area=subj_area,
                open_access_only=open_access_only,
            )

            try:
                resp = scopus_api_request(
                    query=query,
                    api_key=api_key,
                    inst_token=inst_token,
                    view="STANDARD",
                    count=1,
                    start=0,
                )
                sr = resp.get("search-results", {})
                total_res = int(sr.get("opensearch:totalResults", 0) or 0)
                log_line = f"✓ {label_tag} ({entity['name']}): {total_res} publicaciones"
            except Exception as exc:
                total_res = 0
                log_line = f"✗ {label_tag}: Error ({str(exc)[:120]})"

            results.append(
                {
                    "entity_uid": entity.get("entity_uid", ""),
                    "ror_id": entity.get("ror_id", ""),
                    "afid": entity.get("afid", ""),
                    "acronym": entity.get("acronym", ""),
                    "institution_name": entity.get("name", ""),
                    "category": entity.get("category", "University"),
                    "inst_type": entity.get("inst_type", "Public"),
                    "city": entity.get("city", ""),
                    "total_results": total_res,
                    "query_used": query,
                }
            )
            with JOBS_LOCK:
                JOBS[job_id]["logs"].append(log_line)

            if idx < len(entity_refs) - 1 and sleep_time > 0:
                time.sleep(min(sleep_time, 3.0))

        conn = get_connection()
        cur = conn.cursor()
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        cur.execute(
            """
            INSERT INTO comparison_runs
            (title, subtitle, year, subj_area, open_access_only, category_filter, reference_line, source, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                title,
                subtitle,
                year,
                subj_area,
                1 if open_access_only else 0,
                category_filter,
                reference_line,
                "scopus_live_api (AF-ID / ROR)",
                now_str,
            ),
        )
        run_id = cur.lastrowid
        for item in results:
            cur.execute(
                """
                INSERT INTO comparison_items
                (run_id, entity_uid, ror_id, afid, acronym, institution_name,
                 category, inst_type, city, total_results, query_used)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    run_id,
                    item["entity_uid"],
                    item["ror_id"],
                    item["afid"],
                    item["acronym"],
                    item["institution_name"],
                    item["category"],
                    item["inst_type"],
                    item["city"],
                    item["total_results"],
                    item["query_used"],
                ),
            )
        conn.commit()
        conn.close()

        with JOBS_LOCK:
            JOBS[job_id]["percent"] = 100
            JOBS[job_id]["status"] = "completed"
            JOBS[job_id]["result_run_id"] = run_id
            JOBS[job_id]["message"] = f"Completado: {len(results)} entidades procesadas."

    t = threading.Thread(target=_worker, daemon=True)
    t.start()
    return job_id


def start_harvest_job(payload: dict) -> str:
    """
    Launch a background job to harvest detailed publication records for a target entity
    identified by Scopus AF-ID, ROR ID, or `entity_uid`.
    """
    job_id = str(uuid.uuid4())[:8]
    raw_ref = (
        payload.get("custom_identifier", "").strip()
        or payload.get("entity_ref", "").strip()
        or payload.get("institution_name", "").strip()
        or "ror:02veev176"
    )
    year = str(payload.get("year", "2025")).strip()
    subj_area = str(payload.get("subj_area", "ALL")).strip()
    open_access_only = bool(payload.get("open_access_only", False))
    view_mode = str(payload.get("view_mode", "STANDARD")).upper().strip()
    extra_filter = str(payload.get("extra_filter", "")).strip()
    max_records = int(payload.get("max_records", 500) or 500)

    job_state = {
        "id": job_id,
        "type": "harvest",
        "status": "running",
        "title": f"Cosecha Scopus ({raw_ref} · {year})",
        "current": 0,
        "total": 1,
        "percent": 0,
        "message": f"Resolviendo identificador {raw_ref}...",
        "logs": [],
        "result_dataset_id": None,
        "cancelled": False,
        "started_at": datetime.now().strftime("%H:%M:%S"),
    }
    with JOBS_LOCK:
        JOBS[job_id] = job_state

    def _worker():
        settings = get_settings()
        api_key = payload.get("api_key") or settings.get("api_key", "")
        inst_token = settings.get("inst_token", "")
        sleep_time = float(payload.get("sleep_time", settings.get("sleep_time", 1.0)) or 1.0)
        batch_size = 20 if view_mode == "COMPLETE" else 25

        conn = get_connection()
        entity = find_institution(conn, raw_ref)
        conn.close()

        if not entity:
            try:
                resolved = resolve_entity_metadata(
                    ror_id=normalize_ror_id(raw_ref),
                    afid=format_afids(raw_ref),
                    api_key=api_key,
                    inst_token=inst_token,
                )
                conn = get_connection()
                entity = upsert_institution(conn, resolved, allow_provisional=True)
                conn.close()
            except Exception as exc:
                with JOBS_LOCK:
                    JOBS[job_id]["status"] = "error"
                    JOBS[job_id]["message"] = f"Identificador no válido ({raw_ref}): {exc}"
                    JOBS[job_id]["logs"].append(f"✗ {exc}")
                return

        if not normalize_afids(entity.get("afid", "")) and entity.get("afid_status") == "pending":
            ensure_entity_scopus_afid(entity, api_key=api_key, inst_token=inst_token)

        target_afids = set(normalize_afids(entity.get("afid", "")))
        cand_names = _entity_candidate_names(entity)
        if entity.get("acronym"):
            cand_names.append(entity["acronym"])
        fallback_pattern = "|".join(re.escape(nm) for nm in cand_names if nm)

        query = payload.get("custom_query", "").strip() or build_scopus_query(
            entity_ref=entity,
            year=year,
            subj_area=subj_area,
            open_access_only=open_access_only,
            extra_filter=extra_filter,
        )

        id_badge = format_entity_identifier_badge(entity)
        display_header = f"{entity['acronym'] or entity['name']} ({id_badge})"
        with JOBS_LOCK:
            JOBS[job_id]["title"] = f"{display_header} — {year}"
            JOBS[job_id]["message"] = f"Verificando total de publicaciones para {display_header}..."
            JOBS[job_id]["logs"].append(f"Entidad: {entity['name']} [{id_badge}]")
            JOBS[job_id]["logs"].append(f"Query: {query}")

        try:
            init_resp = scopus_api_request(
                query=query,
                api_key=api_key,
                inst_token=inst_token,
                view="STANDARD",
                count=1,
                start=0,
            )
            total_papers = int(init_resp.get("search-results", {}).get("opensearch:totalResults", 0) or 0)
        except Exception as exc:
            with JOBS_LOCK:
                JOBS[job_id]["status"] = "error"
                JOBS[job_id]["message"] = f"Error conectando a Scopus: {str(exc)}"
                JOBS[job_id]["logs"].append(f"✗ Error fatal: {str(exc)}")
            return

        if total_papers == 0:
            with JOBS_LOCK:
                JOBS[job_id]["status"] = "completed"
                JOBS[job_id]["percent"] = 100
                JOBS[job_id]["message"] = "No se encontraron publicaciones para esta consulta."
                JOBS[job_id]["logs"].append("0 publicaciones encontradas.")
            return

        target_total = min(total_papers, max_records)
        start_indices = list(range(0, target_total, batch_size))
        with JOBS_LOCK:
            JOBS[job_id]["total"] = len(start_indices)
            JOBS[job_id]["logs"].append(
                f"Encontradas {total_papers} publicaciones (descargando hasta {target_total} en {len(start_indices)} lotes)..."
            )

        extracted_rows = []
        seen_keys = set()

        for idx, start_offset in enumerate(start_indices):
            with JOBS_LOCK:
                if JOBS[job_id]["cancelled"]:
                    JOBS[job_id]["status"] = "cancelled"
                    JOBS[job_id]["message"] = "Descarga cancelada por el usuario."
                    return
                JOBS[job_id]["current"] = idx + 1
                JOBS[job_id]["percent"] = int(round((idx / max(1, len(start_indices))) * 100))
                JOBS[job_id]["message"] = (
                    f"Descargando lote {idx + 1}/{len(start_indices)} "
                    f"(registros {start_offset + 1}-{min(start_offset + batch_size, target_total)})..."
                )

            try:
                batch_resp = scopus_api_request(
                    query=query,
                    api_key=api_key,
                    inst_token=inst_token,
                    view=view_mode,
                    count=batch_size,
                    start=start_offset,
                )
                entries = batch_resp.get("search-results", {}).get("entry", [])
                if isinstance(entries, dict):
                    entries = [entries]

                batch_added = 0
                for entry in entries:
                    parsed = parse_scopus_entry(
                        entry,
                        target_afids=target_afids,
                        target_pattern=fallback_pattern,
                    )
                    if not parsed:
                        continue
                    dedup_key = (parsed["doi"] or parsed["article_name"]).lower().strip()
                    if dedup_key not in seen_keys:
                        seen_keys.add(dedup_key)
                        extracted_rows.append(parsed)
                        batch_added += 1

                with JOBS_LOCK:
                    JOBS[job_id]["logs"].append(f"✓ Lote {idx + 1}: +{batch_added} artículos extraídos")
            except Exception as exc:
                with JOBS_LOCK:
                    JOBS[job_id]["logs"].append(f"✗ Error en lote {idx + 1}: {str(exc)[:120]}")

            if idx < len(start_indices) - 1 and sleep_time > 0:
                time.sleep(min(sleep_time, 3.0))

        conn = get_connection()
        cur = conn.cursor()
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        ds_title = payload.get("title") or (
            f"{entity.get('acronym') or entity['name']} [{id_badge}] — Publicaciones {year} ({view_mode})"
        )
        cur.execute(
            """
            INSERT INTO harvest_datasets
            (title, entity_uid, ror_id, afid, acronym, institution_name, year, view_mode, query_used, total_records, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                ds_title,
                entity.get("entity_uid", ""),
                entity.get("ror_id", ""),
                entity.get("afid", ""),
                entity.get("acronym", ""),
                entity.get("name", ""),
                year,
                view_mode,
                query,
                len(extracted_rows),
                now_str,
            ),
        )
        ds_id = cur.lastrowid

        for r in extracted_rows:
            cur.execute(
                """
                INSERT INTO publications
                (dataset_id, article_name, journal_name, date_publication, issn_isbn,
                 main_knowledge_area, specific_areas, target_authors, authors_list,
                 affiliations, doi, cited_by)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    ds_id,
                    r["article_name"],
                    r["journal_name"],
                    r["date_publication"],
                    r["issn_isbn"],
                    r["main_knowledge_area"],
                    r["specific_areas"],
                    r["target_authors"],
                    r["authors_list"],
                    r["affiliations"],
                    r["doi"],
                    r["cited_by"],
                ),
            )
        conn.commit()
        conn.close()

        with JOBS_LOCK:
            JOBS[job_id]["percent"] = 100
            JOBS[job_id]["status"] = "completed"
            JOBS[job_id]["result_dataset_id"] = ds_id
            JOBS[job_id]["message"] = f"Descarga completa: {len(extracted_rows)} publicaciones únicas guardadas."

    t = threading.Thread(target=_worker, daemon=True)
    t.start()
    return job_id


def compute_word_frequencies(
    records: list,
    source_field: str = "article_name",
    max_words: int = 120,
    min_freq: int = 1,
    extra_stopwords: str = "",
    split_mode: str = "words",
) -> list:
    """
    Compute word or phrase frequencies for Word Clouds & Text Analytics
    (with bilingual stopword filtering).
    """
    stop_set = set(DEFAULT_STOPWORDS)
    if extra_stopwords:
        for w in re.split(r"[,;\s]+", extra_stopwords.lower()):
            if w.strip():
                stop_set.add(w.strip())

    counter = Counter()
    for row in records:
        text = str(row.get(source_field, "") or "").strip()
        if not text or text.upper() == "NA":
            continue

        if split_mode == "entities" or source_field in ("affiliations", "authors_list"):
            parts = [p.strip() for p in text.split(";") if p.strip()]
            for p in parts:
                if len(p) > 2 and p.lower() not in stop_set:
                    counter[p] += 1
        else:
            words = re.findall(r"[a-zA-ZáéíóúüñÁÉÍÓÚÜÑ]{3,}", text.lower())
            for w in words:
                if w not in stop_set:
                    counter[w] += 1

    filtered = [{"text": k, "value": v} for k, v in counter.most_common() if v >= min_freq]
    return filtered[:max_words]


def generate_csv_bytes(headers: list, rows: list) -> bytes:
    """Create UTF-8 with BOM CSV bytes so Excel opens accented characters properly."""
    buf = io.StringIO()
    writer = csv.writer(buf, quoting=csv.QUOTE_MINIMAL)
    writer.writerow(headers)
    for r in rows:
        writer.writerow(r)
    return ("\ufeff" + buf.getvalue()).encode("utf-8")


def generate_xlsx_bytes(sheet_name: str, headers: list, rows: list) -> bytes:
    """
    Generate a genuine OpenXML (.xlsx) workbook in pure Python using zipfile
    without requiring openpyxl or pandas.
    """
    def col_letter(idx: int) -> str:
        res = ""
        n = idx + 1
        while n > 0:
            n, rem = divmod(n - 1, 26)
            res = chr(65 + rem) + res
        return res

    all_rows = [headers] + rows
    sheet_lines = [
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>',
        '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">',
        "<sheetData>",
    ]

    for r_idx, row in enumerate(all_rows, start=1):
        sheet_lines.append(f'<row r="{r_idx}">')
        for c_idx, val in enumerate(row):
            cell_ref = f"{col_letter(c_idx)}{r_idx}"
            if isinstance(val, (int, float)) and not isinstance(val, bool) and r_idx > 1:
                sheet_lines.append(f'<c r="{cell_ref}"><v>{val}</v></c>')
            else:
                safe_text = xml_escape(str(val if val is not None else ""))
                sheet_lines.append(
                    f'<c r="{cell_ref}" t="inlineStr"><is><t>{safe_text}</t></is></c>'
                )
        sheet_lines.append("</row>")

    sheet_lines.append("</sheetData></worksheet>")
    sheet_xml = "".join(sheet_lines)

    content_types_xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
        '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
        '<Default Extension="xml" ContentType="application/xml"/>'
        '<Override PartName="/xl/workbook.xml" '
        'ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>'
        '<Override PartName="/xl/worksheets/sheet1.xml" '
        'ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>'
        "</Types>"
    )

    rels_xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        '<Relationship Id="rId1" '
        'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" '
        'Target="xl/workbook.xml"/>'
        "</Relationships>"
    )

    safe_sheet = xml_escape(sheet_name[:31] or "ScopusData")
    workbook_xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
        'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
        f'<sheets><sheet name="{safe_sheet}" sheetId="1" r:id="rId1"/></sheets>'
        "</workbook>"
    )

    workbook_rels_xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        '<Relationship Id="rId1" '
        'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" '
        'Target="worksheets/sheet1.xml"/>'
        "</Relationships>"
    )

    out_buf = io.BytesIO()
    with zipfile.ZipFile(out_buf, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("[Content_Types].xml", content_types_xml)
        zf.writestr("_rels/.rels", rels_xml)
        zf.writestr("xl/workbook.xml", workbook_xml)
        zf.writestr("xl/_rels/workbook.xml.rels", workbook_rels_xml)
        zf.writestr("xl/worksheets/sheet1.xml", sheet_xml)

    return out_buf.getvalue()
