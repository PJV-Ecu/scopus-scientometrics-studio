"""
Step 2: Scopus API Client, Asynchronous Job Engine, Text Analytics, and CSV/XLSX Exporters.
Uses only Python standard library modules for zero-dependency reliability.
"""

import csv
import io
import json
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
from xml.sax.saxutils import escape as xml_escape

from database import get_connection

SCOPUS_SEARCH_URL = "https://api.elsevier.com/content/search/scopus"

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


def get_settings() -> dict:
    conn = get_connection()
    rows = conn.execute("SELECT key, value FROM settings").fetchall()
    conn.close()
    settings = {r["key"]: r["value"] for r in rows}
    if not settings.get("api_key"):
        import os
        from database import detect_workspace_api_key
        env_key = os.environ.get("SCOPUS_API_KEY") or os.environ.get("Elsevier_API") or detect_workspace_api_key() or ""
        if env_key.strip():
            settings["api_key"] = env_key.strip()
    return settings


# Institution-specific Scopus disambiguation rules for institutions with international homonyms
# - ROR 01yg1g961: Universidad Nacional de Educación (UNAE, Azogues, Ecuador) vs UNED (Madrid, Spain)
# - ROR 0198j4566: Universidad de Las Américas (UDLA, Quito, Ecuador, AF-ID 60104441) vs UDLA Chile & UDLAP Mexico
INSTITUTION_DISAMBIGUATION_RULES = {
    "universidad nacional de educación": {
        "ror_id": "01yg1g961",
        "afid": "",
        "clause": '(AFFIL("Universidad Nacional de Educación") AND AFFIL("Azogues"))',
    },
    "universidad de las américas": {
        "ror_id": "0198j4566",
        "afid": "60104441",
        "clause": "AF-ID(60104441)",
    },
    "universidad metropolitana": {
        "ror_id": "",
        "afid": "",
        "clause": '(AFFIL("Universidad Metropolitana") AND AFFIL("Guayaquil"))',
    },
    "universidad del pacífico escuela de negocios": {
        "ror_id": "",
        "afid": "",
        "clause": '(AFFIL("Universidad del Pacífico") AND AFFIL("Guayaquil"))',
    },
}


def build_scopus_query(
    institution_name: str,
    year: str = "2025",
    subj_area: str = "ALL",
    open_access_only: bool = False,
    afid: str = "",
    extra_filter: str = "",
    country_filter: str = "Ecuador",
) -> str:
    """Build a valid Scopus boolean search query matching rscopus conventions with ROR/AF-ID disambiguation."""
    norm_name = institution_name.lower().strip()
    if norm_name in INSTITUTION_DISAMBIGUATION_RULES:
        aff_clause = INSTITUTION_DISAMBIGUATION_RULES[norm_name]["clause"]
    elif afid and afid.strip():
        aff_clause = f"AF-ID({afid.strip()})"
    else:
        clean_name = institution_name.replace('"', "").strip()
        aff_clause = f'AFFIL("{clean_name}")'
        if country_filter and country_filter.strip():
            aff_clause += f" AND AFFILCOUNTRY({country_filter.strip()})"

    clauses = [aff_clause]

    if subj_area and subj_area.upper() != "ALL":
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
) -> dict:
    """
    Execute a single Scopus Search API call with retry on transient errors (429/5xx)
    and automatic fallback from COMPLETE to STANDARD view if unauthorized.
    """
    if not api_key or not api_key.strip():
        raise ValueError("Scopus API key is not configured. Please add your API key in Settings.")

    params = {
        "query": query,
        "view": view,
        "count": str(count),
        "start": str(start),
    }
    url = f"{SCOPUS_SEARCH_URL}?{urllib.parse.urlencode(params)}"
    headers = {
        "X-ELS-APIKey": api_key.strip(),
        "Accept": "application/json",
        "User-Agent": "ScopusProductivityStudio/2.0",
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

            # Automatic fallback if COMPLETE view is not authorized for this API key
            if e.code in (401, 403) and view.upper() == "COMPLETE":
                return scopus_api_request(
                    query=query,
                    api_key=api_key,
                    inst_token=inst_token,
                    view="STANDARD",
                    count=count,
                    start=start,
                    max_retries=max_retries,
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


def parse_scopus_entry(entry: dict, target_pattern: str = "") -> dict:
    """
    Extract normalized publication fields from a single Scopus entry object
    (compatible with both STANDARD and COMPLETE views, matching scripts 8, 9, and 10).
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

    # Affiliations
    aff_raw = entry.get("affiliation", [])
    if isinstance(aff_raw, dict):
        aff_raw = [aff_raw]
    aff_names = []
    target_afids = set()
    for a in aff_raw:
        if isinstance(a, dict):
            aname = str(a.get("affilname", "")).strip()
            afid = str(a.get("afid", "")).strip()
            if aname and aname not in aff_names:
                aff_names.append(aname)
            if target_pattern and aname and re.search(target_pattern, aname, re.IGNORECASE):
                if afid:
                    target_afids.add(afid)
    affiliations_str = "; ".join(aff_names)

    # Authors
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

            # Check target institution linkage (COMPLETE view provides author->afid)
            if target_afids:
                afid_field = auth.get("afid", [])
                if isinstance(afid_field, dict):
                    afid_field = [afid_field]
                auth_afids = set()
                for af in afid_field:
                    if isinstance(af, dict):
                        auth_afids.add(str(af.get("$", "")).strip())
                    else:
                        auth_afids.add(str(af).strip())
                if auth_afids.intersection(target_afids) and aname not in target_authors:
                    target_authors.append(aname)

    if not all_authors:
        creator = get_val("dc:creator")
        if creator:
            all_authors.append(creator)

    authors_list_str = "; ".join(all_authors)
    if target_authors:
        target_authors_str = "; ".join(target_authors)
    elif target_pattern and re.search(target_pattern, affiliations_str, re.IGNORECASE):
        target_authors_str = authors_list_str
    else:
        target_authors_str = ""

    # Subject Areas (available in COMPLETE view, fallback to aggregationType in STANDARD view)
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


def start_comparison_job(payload: dict) -> str:
    """Launch a background job to query Scopus total publication counts across a list of institutions."""
    job_id = str(uuid.uuid4())[:8]
    institutions = payload.get("institutions", [])
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
        "total": len(institutions),
        "percent": 0,
        "message": "Iniciando consultas a Scopus...",
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

        conn = get_connection()
        inst_rows = conn.execute("SELECT name, category, inst_type, city, afid FROM institutions").fetchall()
        inst_map = {r["name"]: dict(r) for r in inst_rows}
        conn.close()

        results = []
        for idx, inst_name in enumerate(institutions):
            with JOBS_LOCK:
                if JOBS[job_id]["cancelled"]:
                    JOBS[job_id]["status"] = "cancelled"
                    JOBS[job_id]["message"] = "Consulta cancelada por el usuario."
                    return
                JOBS[job_id]["current"] = idx + 1
                JOBS[job_id]["percent"] = int(round(((idx) / max(1, len(institutions))) * 100))
                JOBS[job_id]["message"] = f"Consultando ({idx + 1}/{len(institutions)}): {inst_name}"

            meta = inst_map.get(inst_name, {"category": "University", "inst_type": "Public", "city": "", "afid": ""})
            query = build_scopus_query(
                institution_name=inst_name,
                year=year,
                subj_area=subj_area,
                open_access_only=open_access_only,
                afid=meta.get("afid", ""),
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
                log_line = f"✓ {inst_name}: {total_res} publicaciones"
            except Exception as exc:
                total_res = 0
                log_line = f"✗ {inst_name}: Error ({str(exc)[:120]})"

            results.append(
                {
                    "institution_name": inst_name,
                    "category": meta.get("category", "University"),
                    "inst_type": meta.get("inst_type", "Public"),
                    "city": meta.get("city", ""),
                    "total_results": total_res,
                    "query_used": query,
                }
            )
            with JOBS_LOCK:
                JOBS[job_id]["logs"].append(log_line)

            if idx < len(institutions) - 1 and sleep_time > 0:
                time.sleep(min(sleep_time, 3.0))

        # Save run to SQLite
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
                "scopus_live_api",
                now_str,
            ),
        )
        run_id = cur.lastrowid
        for item in results:
            cur.execute(
                """
                INSERT INTO comparison_items
                (run_id, institution_name, category, inst_type, city, total_results, query_used)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    run_id,
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
            JOBS[job_id]["message"] = f"Completado: {len(results)} instituciones procesadas."

    t = threading.Thread(target=_worker, daemon=True)
    t.start()
    return job_id


def start_harvest_job(payload: dict) -> str:
    """Launch a background job to harvest detailed publication records for a target institution."""
    job_id = str(uuid.uuid4())[:8]
    inst_name = str(payload.get("institution_name", "Instituto Nacional de Biodiversidad")).strip()
    year = str(payload.get("year", "2025")).strip()
    subj_area = str(payload.get("subj_area", "ALL")).strip()
    open_access_only = bool(payload.get("open_access_only", False))
    view_mode = str(payload.get("view_mode", "STANDARD")).upper().strip()
    target_pattern = str(payload.get("target_pattern", "")).strip() or re.escape(inst_name)
    max_records = int(payload.get("max_records", 500) or 500)

    query = payload.get("custom_query", "").strip() or build_scopus_query(
        institution_name=inst_name,
        year=year,
        subj_area=subj_area,
        open_access_only=open_access_only,
    )

    job_state = {
        "id": job_id,
        "type": "harvest",
        "status": "running",
        "title": f"{inst_name} ({year})",
        "current": 0,
        "total": 1,
        "percent": 0,
        "message": f"Verificando total de publicaciones para {inst_name}...",
        "logs": [f"Query: {query}"],
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
                    parsed = parse_scopus_entry(entry, target_pattern=target_pattern)
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

        # Store dataset in SQLite
        conn = get_connection()
        cur = conn.cursor()
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        ds_title = payload.get("title") or f"{inst_name} — Publicaciones {year} ({view_mode})"
        cur.execute(
            """
            INSERT INTO harvest_datasets
            (title, institution_name, year, view_mode, query_used, total_records, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (ds_title, inst_name, year, view_mode, query, len(extracted_rows), now_str),
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
    (replaces script_wordcloud.R with full bilingual stopword filtering).
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
            # Split by semicolon for institutional affiliations or individual authors
            parts = [p.strip() for p in text.split(";") if p.strip()]
            for p in parts:
                if len(p) > 2 and p.lower() not in stop_set:
                    counter[p] += 1
        else:
            # Tokenize words (preserving Spanish accents)
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

