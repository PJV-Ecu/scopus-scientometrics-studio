#!/usr/bin/env python3
"""
Main HTTP Server & REST API for Scopus Scientific Productivity & Visualization Studio.
Runs with Python 3.10+ standard library (ThreadingHTTPServer).
"""

import json
import mimetypes
import os
import re
import sys
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE_DIR))

from database import get_connection, init_db
from scopus_client import (
    JOBS,
    JOBS_LOCK,
    build_scopus_query,
    compute_word_frequencies,
    generate_csv_bytes,
    generate_xlsx_bytes,
    get_settings,
    scopus_api_request,
    start_comparison_job,
    start_harvest_job,
)

STATIC_DIR = BASE_DIR / "static"


class ScopusStudioHandler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def _is_authenticated(self) -> bool:
        """Check HTTP Basic Auth if APP_PASSWORD environment variable is set."""
        app_pwd = os.environ.get("APP_PASSWORD", "").strip()
        if not app_pwd:
            return True  # No password configured, open mode

        app_user = os.environ.get("APP_USERNAME", "admin").strip()
        auth_header = self.headers.get("Authorization", "")
        if not auth_header.startswith("Basic "):
            return False

        import base64
        import hmac
        try:
            decoded = base64.b64decode(auth_header[6:]).decode("utf-8")
            user, pwd = decoded.split(":", 1)
            return hmac.compare_digest(user, app_user) and hmac.compare_digest(pwd, app_pwd)
        except Exception:
            return False

    def _send_auth_required(self):
        self.send_response(401)
        self.send_header('WWW-Authenticate', 'Basic realm="Scopus Scientometrics Studio - Restricted Access"')
        self.send_header("Content-Type", "text/html; charset=utf-8")
        body = (
            "<!DOCTYPE html><html><body style='font-family:sans-serif;text-align:center;padding:50px;'>"
            "<h2>401 Unauthorized</h2>"
            "<p>Acceso restringido. Por favor ingrese el usuario y contraseña del sistema.</p>"
            "</body></html>"
        ).encode("utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, fmt, *args):
        # Clean concise logging
        sys.stderr.write(f"[ScopusStudio] {self.address_string()} - {fmt % args}\n")

    def _send_json(self, data: dict, status: int = 200) -> None:
        raw = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(raw)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(raw)

    def _send_bytes(self, raw: bytes, content_type: str, filename: str = "") -> None:
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(raw)))
        if filename:
            self.send_header("Content-Disposition", f'attachment; filename="{filename}"')
        self.end_headers()
        self.wfile.write(raw)

    def _read_json_body(self) -> dict:
        length = int(self.headers.get("Content-Length", 0) or 0)
        if length <= 0:
            return {}
        raw = self.rfile.read(length).decode("utf-8", errors="replace")
        try:
            return json.loads(raw)
        except Exception:
            return {}

    def do_GET(self):
        if not self._is_authenticated():
            return self._send_auth_required()

        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path
        query_params = urllib.parse.parse_qs(parsed.query)

        if path == "/api/bootstrap":
            return self._handle_bootstrap()

        if path.startswith("/api/comparisons/"):
            run_id_str = path.split("/")[-1]
            if run_id_str.isdigit():
                return self._handle_get_comparison(int(run_id_str))

        if path.startswith("/api/datasets/"):
            parts = [p for p in path.split("/") if p]
            if len(parts) == 3 and parts[2].isdigit():
                return self._handle_get_dataset(int(parts[2]))

        if path.startswith("/api/jobs/"):
            job_id = path.split("/")[-1]
            with JOBS_LOCK:
                job = JOBS.get(job_id)
                if not job:
                    return self._send_json({"error": "Job not found"}, 404)
                return self._send_json(dict(job))

        if path.startswith("/api/export/comparison/"):
            run_id_str = path.split("/")[-1]
            fmt = query_params.get("format", ["csv"])[0].lower()
            if run_id_str.isdigit():
                return self._handle_export_comparison(int(run_id_str), fmt)

        if path.startswith("/api/export/dataset/"):
            ds_id_str = path.split("/")[-1]
            fmt = query_params.get("format", ["csv"])[0].lower()
            if ds_id_str.isdigit():
                return self._handle_export_dataset(int(ds_id_str), fmt)

        # Serve static frontend files
        return self._serve_static(path)

    def do_POST(self):
        if not self._is_authenticated():
            return self._send_auth_required()

        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path
        body = self._read_json_body()

        if path == "/api/settings":
            return self._handle_save_settings(body)

        if path == "/api/test-key":
            return self._handle_test_key(body)

        if path == "/api/preview-query":
            q = build_scopus_query(
                institution_name=body.get("institution_name", "Pontificia Universidad Católica del Ecuador"),
                year=body.get("year", "2025"),
                subj_area=body.get("subj_area", "ALL"),
                open_access_only=bool(body.get("open_access_only", False)),
                afid=body.get("afid", ""),
                extra_filter=body.get("extra_filter", ""),
            )
            return self._send_json({"query": q})

        if path == "/api/institutions":
            return self._handle_add_institution(body)

        if path == "/api/jobs/comparison":
            job_id = start_comparison_job(body)
            return self._send_json({"job_id": job_id})

        if path == "/api/jobs/harvest":
            job_id = start_harvest_job(body)
            return self._send_json({"job_id": job_id})

        if path.startswith("/api/jobs/") and path.endswith("/cancel"):
            job_id = path.split("/")[-2]
            with JOBS_LOCK:
                if job_id in JOBS:
                    JOBS[job_id]["cancelled"] = True
                    return self._send_json({"ok": True})
            return self._send_json({"error": "Job not found"}, 404)

        if path.startswith("/api/datasets/") and path.endswith("/wordcloud"):
            ds_id_str = path.split("/")[-2]
            if ds_id_str.isdigit():
                return self._handle_dataset_wordcloud(int(ds_id_str), body)

        if path == "/api/comparisons/update-item":
            return self._handle_update_comparison_item(body)

        return self._send_json({"error": "Not found"}, 404)

    def do_DELETE(self):
        if not self._is_authenticated():
            return self._send_auth_required()

        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path

        if path.startswith("/api/comparisons/"):
            run_id_str = path.split("/")[-1]
            if run_id_str.isdigit():
                conn = get_connection()
                conn.execute("DELETE FROM comparison_items WHERE run_id = ?", (int(run_id_str),))
                conn.execute("DELETE FROM comparison_runs WHERE id = ?", (int(run_id_str),))
                conn.commit()
                conn.close()
                return self._send_json({"ok": True})

        if path.startswith("/api/datasets/"):
            ds_id_str = path.split("/")[-1]
            if ds_id_str.isdigit():
                conn = get_connection()
                conn.execute("DELETE FROM publications WHERE dataset_id = ?", (int(ds_id_str),))
                conn.execute("DELETE FROM harvest_datasets WHERE id = ?", (int(ds_id_str),))
                conn.commit()
                conn.close()
                return self._send_json({"ok": True})

        if path.startswith("/api/institutions/"):
            inst_id_str = path.split("/")[-1]
            if inst_id_str.isdigit():
                conn = get_connection()
                conn.execute("DELETE FROM institutions WHERE id = ?", (int(inst_id_str),))
                conn.commit()
                conn.close()
                return self._send_json({"ok": True})

        return self._send_json({"error": "Not found"}, 404)

    def _handle_bootstrap(self):
        settings = get_settings()
        raw_key = settings.get("api_key", "")
        masked_key = (raw_key[:6] + "••••••••••••••••••••" + raw_key[-4:]) if len(raw_key) >= 12 else ""

        conn = get_connection()
        subject_areas = [
            dict(r) for r in conn.execute("SELECT code, name_en, name_es FROM subject_areas").fetchall()
        ]
        institutions = [
            dict(r)
            for r in conn.execute(
                "SELECT id, name, category, inst_type, city, afid, aliases FROM institutions ORDER BY category DESC, name ASC"
            ).fetchall()
        ]
        comparison_runs = [
            dict(r)
            for r in conn.execute(
                """
                SELECT r.*, COUNT(i.id) as institution_count, COALESCE(SUM(i.total_results), 0) as sum_publications
                FROM comparison_runs r
                LEFT JOIN comparison_items i ON i.run_id = r.id
                GROUP BY r.id
                ORDER BY r.id DESC
                """
            ).fetchall()
        ]
        harvest_datasets = [
            dict(r)
            for r in conn.execute(
                "SELECT * FROM harvest_datasets ORDER BY id DESC"
            ).fetchall()
        ]
        conn.close()

        return self._send_json(
            {
                "settings": {
                    "has_api_key": bool(raw_key),
                    "masked_api_key": masked_key,
                    "inst_token": settings.get("inst_token", ""),
                    "sleep_time": settings.get("sleep_time", "1.0"),
                    "default_view": settings.get("default_view", "STANDARD"),
                },
                "subject_areas": subject_areas,
                "institutions": institutions,
                "comparison_runs": comparison_runs,
                "harvest_datasets": harvest_datasets,
            }
        )

    def _handle_get_comparison(self, run_id: int):
        conn = get_connection()
        run = conn.execute("SELECT * FROM comparison_runs WHERE id = ?", (run_id,)).fetchone()
        if not run:
            conn.close()
            return self._send_json({"error": "Comparison run not found"}, 404)
        items = [
            dict(r)
            for r in conn.execute(
                "SELECT * FROM comparison_items WHERE run_id = ? ORDER BY total_results DESC, institution_name ASC",
                (run_id,),
            ).fetchall()
        ]
        conn.close()
        return self._send_json({"run": dict(run), "items": items})

    def _handle_get_dataset(self, ds_id: int):
        conn = get_connection()
        ds = conn.execute("SELECT * FROM harvest_datasets WHERE id = ?", (ds_id,)).fetchone()
        if not ds:
            conn.close()
            return self._send_json({"error": "Dataset not found"}, 404)
        pubs = [
            dict(r)
            for r in conn.execute(
                "SELECT * FROM publications WHERE dataset_id = ? ORDER BY date_publication DESC, id ASC",
                (ds_id,),
            ).fetchall()
        ]
        conn.close()
        return self._send_json({"dataset": dict(ds), "publications": pubs})

    def _handle_dataset_wordcloud(self, ds_id: int, body: dict):
        conn = get_connection()
        pubs = [
            dict(r)
            for r in conn.execute("SELECT * FROM publications WHERE dataset_id = ?", (ds_id,)).fetchall()
        ]
        conn.close()
        source_field = body.get("source_field", "article_name")
        max_words = int(body.get("max_words", 100) or 100)
        min_freq = int(body.get("min_freq", 1) or 1)
        extra_stopwords = body.get("extra_stopwords", "")
        split_mode = body.get("split_mode", "words")

        freqs = compute_word_frequencies(
            records=pubs,
            source_field=source_field,
            max_words=max_words,
            min_freq=min_freq,
            extra_stopwords=extra_stopwords,
            split_mode=split_mode,
        )
        return self._send_json({"words": freqs, "total_documents": len(pubs)})

    def _handle_save_settings(self, body: dict):
        conn = get_connection()
        cur = conn.cursor()
        for key in ("api_key", "inst_token", "sleep_time", "default_view"):
            if key in body and body[key] is not None:
                val = str(body[key]).strip()
                if key == "api_key" and ("•" in val or val == ""):
                    if val == "":
                        cur.execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)", (key, ""))
                    continue
                cur.execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)", (key, val))
        conn.commit()
        conn.close()
        return self._handle_bootstrap()

    def _handle_test_key(self, body: dict):
        settings = get_settings()
        api_key = body.get("api_key", "").strip()
        if not api_key or "•" in api_key:
            api_key = settings.get("api_key", "")
        inst_token = body.get("inst_token", settings.get("inst_token", ""))

        try:
            resp = scopus_api_request(
                query='AFFIL("Instituto Nacional de Biodiversidad") AND PUBYEAR = 2025',
                api_key=api_key,
                inst_token=inst_token,
                view="STANDARD",
                count=1,
            )
            total = resp.get("search-results", {}).get("opensearch:totalResults", "0")
            return self._send_json(
                {
                    "ok": True,
                    "message": f"Conexión exitosa con Scopus API (Prueba INABIO 2025: {total} resultados).",
                }
            )
        except Exception as exc:
            return self._send_json({"ok": False, "message": str(exc)}, 200)

    def _handle_add_institution(self, body: dict):
        name = str(body.get("name", "")).strip()
        if not name:
            return self._send_json({"error": "El nombre de la institución es obligatorio."}, 400)
        category = str(body.get("category", "University")).strip()
        inst_type = str(body.get("inst_type", "Public")).strip()
        city = str(body.get("city", "")).strip()
        afid = str(body.get("afid", "")).strip()
        aliases = str(body.get("aliases", "")).strip()

        conn = get_connection()
        conn.execute(
            """
            INSERT OR REPLACE INTO institutions (name, category, inst_type, city, afid, aliases)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (name, category, inst_type, city, afid, aliases),
        )
        conn.commit()
        conn.close()
        return self._handle_bootstrap()

    def _handle_update_comparison_item(self, body: dict):
        run_id = int(body.get("run_id", 0) or 0)
        reference_line = body.get("reference_line")
        title = body.get("title")
        subtitle = body.get("subtitle")
        conn = get_connection()
        if reference_line is not None:
            conn.execute("UPDATE comparison_runs SET reference_line = ? WHERE id = ?", (float(reference_line), run_id))
        if title:
            conn.execute("UPDATE comparison_runs SET title = ? WHERE id = ?", (str(title).strip(), run_id))
        if subtitle is not None:
            conn.execute("UPDATE comparison_runs SET subtitle = ? WHERE id = ?", (str(subtitle).strip(), run_id))
        conn.commit()
        conn.close()
        return self._handle_get_comparison(run_id)

    def _handle_export_comparison(self, run_id: int, fmt: str):
        conn = get_connection()
        run = conn.execute("SELECT * FROM comparison_runs WHERE id = ?", (run_id,)).fetchone()
        if not run:
            conn.close()
            return self._send_json({"error": "Not found"}, 404)
        items = conn.execute(
            "SELECT * FROM comparison_items WHERE run_id = ? ORDER BY total_results DESC",
            (run_id,),
        ).fetchall()
        conn.close()

        headers = ["Rank", "Institution", "Category", "Type", "City", "Year", "Subject_Area", "Total_Results", "Scopus_Query"]
        rows = [
            [
                idx,
                r["institution_name"],
                r["category"],
                r["inst_type"],
                r["city"],
                run["year"],
                run["subj_area"],
                r["total_results"],
                r["query_used"],
            ]
            for idx, r in enumerate(items, start=1)
        ]

        safe_name = re.sub(r"[^a-zA-Z0-9_-]+", "_", f"Scopus_Comparison_{run['year']}_{run['subj_area']}")
        if fmt == "xlsx":
            raw = generate_xlsx_bytes("Scopus_Comparison", headers, rows)
            return self._send_bytes(
                raw,
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                f"{safe_name}.xlsx",
            )
        raw = generate_csv_bytes(headers, rows)
        return self._send_bytes(raw, "text/csv; charset=utf-8", f"{safe_name}.csv")

    def _handle_export_dataset(self, ds_id: int, fmt: str):
        conn = get_connection()
        ds = conn.execute("SELECT * FROM harvest_datasets WHERE id = ?", (ds_id,)).fetchone()
        if not ds:
            conn.close()
            return self._send_json({"error": "Not found"}, 404)
        pubs = conn.execute(
            "SELECT * FROM publications WHERE dataset_id = ? ORDER BY date_publication DESC, id ASC",
            (ds_id,),
        ).fetchall()
        conn.close()

        headers = [
            "Article_Name",
            "Journal_Name",
            "Date_Publication",
            "ISSN_ISBN",
            "Main_Knowledge_Area",
            "Specific_Areas",
            "Target_Institution_Authors",
            "Authors_List",
            "Affiliations",
            "DOI",
            "Cited_By",
        ]
        rows = [
            [
                p["article_name"],
                p["journal_name"],
                p["date_publication"],
                p["issn_isbn"],
                p["main_knowledge_area"],
                p["specific_areas"],
                p["target_authors"],
                p["authors_list"],
                p["affiliations"],
                p["doi"],
                p["cited_by"],
            ]
            for p in pubs
        ]

        safe_name = re.sub(
            r"[^a-zA-Z0-9_-]+", "_", f"Publications_{ds['institution_name'][:25]}_{ds['year']}"
        )
        if fmt == "xlsx":
            raw = generate_xlsx_bytes("Publications", headers, rows)
            return self._send_bytes(
                raw,
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                f"{safe_name}.xlsx",
            )
        raw = generate_csv_bytes(headers, rows)
        return self._send_bytes(raw, "text/csv; charset=utf-8", f"{safe_name}.csv")

    def _serve_static(self, req_path: str):
        if req_path in ("", "/"):
            req_path = "/index.html"
        target = (STATIC_DIR / req_path.lstrip("/")).resolve()
        if not str(target).startswith(str(STATIC_DIR.resolve())) or not target.is_file():
            self.send_response(404)
            self.end_headers()
            return

        ctype, _ = mimetypes.guess_type(str(target))
        ctype = ctype or "application/octet-stream"
        if ctype.startswith("text/") or ctype in ("application/javascript", "image/svg+xml"):
            ctype += "; charset=utf-8"
        raw = target.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(raw)))
        self.send_header("Cache-Control", "no-cache")
        self.end_headers()
        self.wfile.write(raw)


def main():
    init_db()
    port = int(os.environ.get("PORT", "7860" if os.environ.get("SPACE_ID") else "8080"))
    server = ThreadingHTTPServer(("0.0.0.0", port), ScopusStudioHandler)
    print(f"============================================================")
    print(f" Scopus Scientific Productivity & Visualization Studio")
    print(f" Server listening at: http://localhost:{port}")
    print(f"============================================================")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down server...")
        server.server_close()


if __name__ == "__main__":
    main()

