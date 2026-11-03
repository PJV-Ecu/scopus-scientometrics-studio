"""
Step 1: Database & Seed Data Layer for Scopus Scientific Productivity Studio.
Manages institutions, Scopus subject areas, comparative runs, harvested publication
datasets, and application settings using Python's built-in sqlite3 module.
"""

import csv
import gzip
import json
import os
import re
import sqlite3
import zipfile
import xml.etree.ElementTree as ET
from datetime import datetime
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
WORKSPACE_DIR = BASE_DIR.parent
DATA_DIR = BASE_DIR / "data"
DB_PATH = DATA_DIR / "scopus_studio.db"


SCOPUS_SUBJECT_AREAS = [
    ("ALL", "All Subject Areas", "Todas las áreas del conocimiento"),
    ("AGRI", "Agricultural and Biological Sciences", "Agricultura y Ciencias Biológicas"),
    ("ARTS", "Arts and Humanities", "Artes y Humanidades"),
    ("BIOC", "Biochemistry, Genetics and Molecular Biology", "Bioquímica, Genética y Biología Molecular"),
    ("BUSI", "Business, Management and Accounting", "Negocios, Administración y Contabilidad"),
    ("CENG", "Chemical Engineering", "Ingeniería Química"),
    ("CHEM", "Chemistry", "Química"),
    ("COMP", "Computer Science", "Ciencias de la Computación"),
    ("DECI", "Decision Sciences", "Ciencias de la Decisión"),
    ("DENT", "Dentistry", "Odontología"),
    ("EART", "Earth and Planetary Sciences", "Ciencias de la Tierra y Planetarias"),
    ("ECON", "Economics, Econometrics and Finance", "Economía, Econometría y Finanzas"),
    ("ENER", "Energy", "Energía"),
    ("ENGI", "Engineering", "Ingeniería"),
    ("ENVI", "Environmental Science", "Ciencias Ambientales"),
    ("HEAL", "Health Professions", "Profesiones de la Salud"),
    ("IMMU", "Immunology and Microbiology", "Inmunología y Microbiología"),
    ("MATE", "Materials Science", "Ciencia de los Materiales"),
    ("MATH", "Mathematics", "Matemáticas"),
    ("MEDI", "Medicine", "Medicina"),
    ("NEUR", "Neuroscience", "Neurociencia"),
    ("NURS", "Nursing", "Enfermería"),
    ("PHAR", "Pharmacology, Toxicology and Pharmaceutics", "Farmacología, Toxicología y Farmacéutica"),
    ("PHYS", "Physics and Astronomy", "Física y Astronomía"),
    ("PSYC", "Psychology", "Psicología"),
    ("SOCI", "Social Sciences", "Ciencias Sociales"),
    ("VETE", "Veterinary", "Veterinaria"),
    ("MULT", "Multidisciplinary", "Multidisciplinario"),
]

# Full list of 63 Ecuadorian Universities from script4.R + university_list.xlsx metadata + 2024 benchmark counts
ECUADOR_UNIVERSITIES_SEED = [
    ("Universidad de Las Américas", "University", "Private", "Quito", 1142),
    ("Universidad Nacional de Educación", "University", "Public", "Azogues", 881),
    ("Universidad San Francisco de Quito", "University", "Private", "Quito", 668),
    ("Escuela Superior Politécnica del Litoral", "University", "Public", "Guayaquil", 459),
    ("Escuela Politécnica Nacional", "University", "Public", "Quito", 422),
    ("Universidad Técnica Particular de Loja", "University", "Private", "Loja", 412),
    ("Universidad Politécnica Salesiana", "University", "Private", "Cuenca", 386),
    ("Pontificia Universidad Católica del Ecuador", "University", "Private", "Quito", 382),
    ("Universidad Regional Autónoma de los Andes", "University", "Private", "Ambato", 371),
    ("Escuela Superior Politécnica de Chimborazo", "University", "Public", "Riobamba", 336),
    ("Universidad de las Fuerzas Armadas", "University", "Public", "Sangolquí", 318),
    ("Universidad Técnica de Manabí", "University", "Public", "Portoviejo", 268),
    ("Universidad Técnica de Ambato", "University", "Public", "Ambato", 261),
    ("Universidad Metropolitana", "University", "Private", "Guayaquil", 254),
    ("Universidad Nacional de Chimborazo", "University", "Public", "Riobamba", 238),
    ("Universidad de Cuenca", "University", "Public", "Cuenca", 236),
    ("Universidad Central del Ecuador", "University", "Public", "Quito", 234),
    ("Universidad de Guayaquil", "University", "Public", "Guayaquil", 198),
    ("Universidad del Azuay", "University", "Private", "Cuenca", 162),
    ("Universidad UTE", "University", "Private", "Quito", 148),
    ("Universidad Estatal de Milagro", "University", "Public", "Milagro", 145),
    ("Universidad Internacional del Ecuador", "University", "Private", "Quito", 141),
    ("Universidad Católica de Cuenca", "University", "Private", "Cuenca", 137),
    ("Universidad Tecnológica Indoamérica", "University", "Private", "Ambato", 116),
    ("Universidad Técnica de Cotopaxi", "University", "Public", "Latacunga", 112),
    ("Universidad Técnica del Norte", "University", "Public", "Ibarra", 104),
    ("Universidad Bolivariana del Ecuador", "University", "Private", "Durán", 96),
    ("Universidad Católica de Santiago de Guayaquil", "University", "Private", "Guayaquil", 94),
    ("Facultad Latinoamericana de Ciencias Sociales", "University", "Public", "Quito", 91),
    ("Universidad Estatal Península de Santa Elena", "University", "Public", "La Libertad", 86),
    ("Universidad Técnica Estatal de Quevedo", "University", "Public", "Quevedo", 84),
    ("Universidad Nacional de Loja", "University", "Public", "Loja", 82),
    ("Universidad Regional Amazónica Ikiam", "University", "Public", "Tena", 71),
    ("Universidad Estatal Amazónica", "University", "Public", "Puyo", 64),
    ("Universidad Laica Eloy Alfaro de Manabí", "University", "Public", "Manta", 58),
    ("Universidad Técnica de Machala", "University", "Public", "Machala", 46),
    ("Escuela Superior Politécnica Agropecuaria de Manabí", "University", "Public", "Calceta", 39),
    ("Universidad Andina Simón Bolívar", "University", "Public", "Quito", 38),
    ("Universidad Agraria del Ecuador", "University", "Public", "Guayaquil", 37),
    ("Universidad Estatal del Sur de Manabí", "University", "Public", "Jipijapa", 35),
    ("Universidad Estatal de Bolívar", "University", "Public", "Guaranda", 29),
    ("Universidad Técnica de Babahoyo", "University", "Public", "Babahoyo", 27),
    ("Universidad Tecnológica Israel", "University", "Private", "Quito", 21),
    ("Universidad Tecnológica ECOTEC", "University", "Private", "Samborondón", 19),
    ("Universidad Politécnica Estatal del Carchi", "University", "Public", "Tulcán", 18),
    ("Instituto de Altos Estudios Nacionales", "University", "Public", "Quito", 17),
    ("Universidad Tecnológica Empresarial de Guayaquil", "University", "Private", "Guayaquil", 15),
    ("Universidad de las Artes", "University", "Public", "Guayaquil", 14),
    ("Universidad de Investigación de Tecnología Experimental Yachay", "University", "Public", "Urcuquí", 14),
    ("Universidad de los Hemisferios", "University", "Private", "Quito", 13),
    ("Universidad de Especialidades Turísticas", "University", "Private", "Quito", 12),
    ("Universidad Casa Grande", "University", "Private", "Guayaquil", 11),
    ("Universidad Intercultural de las Nacionalidades Y Pueblos Indígenas Amawtay Wasi", "University", "Public", "Quito", 10),
    ("Universidad Técnica Luis Vargas Torres de Esmeraldas", "University", "Public", "Esmeraldas", 9),
    ("Universidad de Otavalo", "University", "Private", "Otavalo", 8),
    ("Universidad Laica Vicente Rocafuerte de Guayaquil", "University", "Private", "Guayaquil", 7),
    ("Universidad Iberoamericana del Ecuador", "University", "Private", "Quito", 6),
    ("Universidad Particular San Gregorio de Portoviejo", "University", "Private", "Portoviejo", 5),
    ("Universidad Particular Internacional SEK", "University", "Private", "Quito", 4),
    ("Universidad del Río", "University", "Private", "Guayaquil", 3),
    ("Universidad Particular de Especialidades Espíritu Santo", "University", "Private", "Samborondón", 2),
    ("Universidad del Pacífico Escuela de Negocios", "University", "Private", "Guayaquil", 1),
    ("Universidad de Seguridad Ciudadana y Ciencias Policiales", "University", "Public", "Quito", 0),
]

PUBLIC_RESEARCH_INSTITUTES_SEED = [
    ("Instituto Nacional de Biodiversidad", "Research Institute", "Public", "Quito", 88),
    ("Instituto Nacional de Investigaciones Agropecuarias", "Research Institute", "Public", "Quito", 44),
    ("Instituto Nacional de Investigación en Salud Pública", "Research Institute", "Public", "Guayaquil", 23),
    ("Instituto de Investigación Geológico y Energético", "Research Institute", "Public", "Quito", 17),
    ("Instituto Nacional de Patrimonio Cultural", "Research Institute", "Public", "Quito", 5),
    ("Instituto Nacional de Meteorología e Hidrología", "Research Institute", "Public", "Quito", 2),
]

AGRI_COMPARISON_SEED = [
    ("Universidad de Las Américas", 197),
    ("Universidad San Francisco de Quito", 119),
    ("Pontificia Universidad Católica del Ecuador", 89),
    ("Instituto Nacional de Biodiversidad", 86),
    ("Universidad de las Fuerzas Armadas", 30),
    ("Universidad Regional Amazónica Ikiam", 26),
]


def get_connection() -> sqlite3.Connection:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def detect_workspace_api_key() -> str:
    """Detect existing Scopus API key from environment, .Renviron, or worksopace.RData."""
    for env_var in ("SCOPUS_API_KEY", "Elsevier_API", "ELSEVIER_API_KEY"):
        val = os.environ.get(env_var, "").strip()
        if val:
            return val

    renviron_paths = [
        WORKSPACE_DIR / ".Renviron",
        Path.home() / ".Renviron",
    ]
    for rp in renviron_paths:
        try:
            if rp.exists():
                text = rp.read_text(encoding="utf-8", errors="ignore")
                m = re.search(r"(?:Elsevier_API|SCOPUS_API_KEY)\s*=\s*['\"]?([a-fA-F0-9]{32})['\"]?", text)
                if m:
                    return m.group(1)
        except Exception:
            pass

    rdata_path = WORKSPACE_DIR / "worksopace.RData"
    if rdata_path.exists():
        try:
            with gzip.open(rdata_path, "rb") as f:
                raw = f.read()
            m = re.search(rb"[a-f0-9]{32}", raw)
            if m:
                return m.group(0).decode("ascii")
        except Exception:
            pass

    return ""


def init_db() -> None:
    """Create tables and seed initial institutions, subject areas, and historical runs."""
    conn = get_connection()
    cur = conn.cursor()

    cur.executescript(
        """
        CREATE TABLE IF NOT EXISTS settings (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS subject_areas (
            code TEXT PRIMARY KEY,
            name_en TEXT NOT NULL,
            name_es TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS institutions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT UNIQUE NOT NULL,
            category TEXT NOT NULL DEFAULT 'University',
            inst_type TEXT NOT NULL DEFAULT 'Public',
            city TEXT DEFAULT '',
            afid TEXT DEFAULT '',
            aliases TEXT DEFAULT '',
            active INTEGER NOT NULL DEFAULT 1
        );

        CREATE TABLE IF NOT EXISTS comparison_runs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            subtitle TEXT DEFAULT '',
            year TEXT NOT NULL,
            subj_area TEXT NOT NULL DEFAULT 'ALL',
            open_access_only INTEGER NOT NULL DEFAULT 0,
            category_filter TEXT DEFAULT 'ALL',
            reference_line REAL DEFAULT 0,
            source TEXT DEFAULT 'scopus_api',
            created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS comparison_items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            run_id INTEGER NOT NULL,
            institution_name TEXT NOT NULL,
            category TEXT DEFAULT 'University',
            inst_type TEXT DEFAULT 'Public',
            city TEXT DEFAULT '',
            total_results INTEGER NOT NULL DEFAULT 0,
            query_used TEXT DEFAULT '',
            FOREIGN KEY (run_id) REFERENCES comparison_runs(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS harvest_datasets (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            institution_name TEXT NOT NULL,
            year TEXT NOT NULL,
            view_mode TEXT NOT NULL DEFAULT 'STANDARD',
            query_used TEXT NOT NULL,
            total_records INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS publications (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            dataset_id INTEGER NOT NULL,
            article_name TEXT NOT NULL,
            journal_name TEXT DEFAULT '',
            date_publication TEXT DEFAULT '',
            issn_isbn TEXT DEFAULT '',
            main_knowledge_area TEXT DEFAULT '',
            specific_areas TEXT DEFAULT '',
            target_authors TEXT DEFAULT '',
            authors_list TEXT DEFAULT '',
            affiliations TEXT DEFAULT '',
            doi TEXT DEFAULT '',
            cited_by INTEGER DEFAULT 0,
            FOREIGN KEY (dataset_id) REFERENCES harvest_datasets(id) ON DELETE CASCADE
        );
        """
    )

    # Seed settings
    cur.execute("SELECT COUNT(*) FROM settings")
    if cur.fetchone()[0] == 0:
        detected_key = detect_workspace_api_key()
        default_settings = {
            "api_key": detected_key,
            "inst_token": "",
            "sleep_time": "1.0",
            "default_view": "STANDARD",
            "batch_size": "25",
        }
        for k, v in default_settings.items():
            cur.execute("INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?)", (k, v))

    # Seed subject areas
    cur.execute("SELECT COUNT(*) FROM subject_areas")
    if cur.fetchone()[0] == 0:
        cur.executemany(
            "INSERT OR IGNORE INTO subject_areas (code, name_en, name_es) VALUES (?, ?, ?)",
            SCOPUS_SUBJECT_AREAS,
        )

    # Seed institutions
    cur.execute("SELECT COUNT(*) FROM institutions")
    if cur.fetchone()[0] == 0:
        # Also enrich city/type from university_list.xlsx if present
        xlsx_meta = _read_university_xlsx_metadata()
        for name, cat, itype, city, _ in ECUADOR_UNIVERSITIES_SEED:
            norm = name.lower().strip()
            if norm in xlsx_meta:
                itype = xlsx_meta[norm].get("type", itype) or itype
                city = xlsx_meta[norm].get("city", city) or city
            aliases = "INABIO" if "Biodiversidad" in name else ""
            cur.execute(
                """
                INSERT OR IGNORE INTO institutions (name, category, inst_type, city, aliases)
                VALUES (?, ?, ?, ?, ?)
                """,
                (name, cat, itype, city, aliases),
            )
        for name, cat, itype, city, _ in PUBLIC_RESEARCH_INSTITUTES_SEED:
            aliases = "INABIO" if "Biodiversidad" in name else ""
            cur.execute(
                """
                INSERT OR IGNORE INTO institutions (name, category, inst_type, city, aliases)
                VALUES (?, ?, ?, ?, ?)
                """,
                (name, cat, itype, city, aliases),
            )

    # Seed historical comparison runs from workspace outputs
    cur.execute("SELECT COUNT(*) FROM comparison_runs")
    if cur.fetchone()[0] == 0:
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        # 1) Public Research Institutes (plot3.svg / script3.R)
        cur.execute(
            """
            INSERT INTO comparison_runs
            (title, subtitle, year, subj_area, open_access_only, category_filter, reference_line, source, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "Publicaciones en todas las áreas — Institutos Públicos",
                "Comparativa de institutos públicos de investigación del Ecuador (Scopus)",
                "2025",
                "ALL",
                0,
                "Research Institute",
                65.0,
                "workspace_seed (script3.R / plot3.svg)",
                now_str,
            ),
        )
        run1_id = cur.lastrowid
        for name, cat, itype, city, count in PUBLIC_RESEARCH_INSTITUTES_SEED:
            q = f'AFFIL("{name}") AND PUBYEAR = 2025'
            cur.execute(
                """
                INSERT INTO comparison_items
                (run_id, institution_name, category, inst_type, city, total_results, query_used)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (run1_id, name, cat, itype, city, count, q),
            )

        # 2) Universities & INABIO in Agriculture & Biological Sciences (script2.R / worksopace.RData)
        cur.execute(
            """
            INSERT INTO comparison_runs
            (title, subtitle, year, subj_area, open_access_only, category_filter, reference_line, source, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "Publicaciones en Agricultura y Ciencias Biológicas (AGRI)",
                "Comparativa de universidades seleccionadas e INABIO en el área AGRI",
                "2025",
                "AGRI",
                0,
                "Custom",
                65.0,
                "workspace_seed (script2.R / worksopace.RData)",
                now_str,
            ),
        )
        run2_id = cur.lastrowid
        inst_lookup = {r[0]: (r[1], r[2], r[3]) for r in ECUADOR_UNIVERSITIES_SEED + PUBLIC_RESEARCH_INSTITUTES_SEED}
        for name, count in AGRI_COMPARISON_SEED:
            cat, itype, city = inst_lookup.get(name, ("University", "Public", "Quito"))
            q = f'AFFIL("{name}") AND SUBJAREA(AGRI) AND PUBYEAR = 2025'
            cur.execute(
                """
                INSERT INTO comparison_items
                (run_id, institution_name, category, inst_type, city, total_results, query_used)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (run2_id, name, cat, itype, city, count, q),
            )

        # 3) All 63 Ecuadorian Universities (script4.R / plot_pomological.R)
        cur.execute(
            """
            INSERT INTO comparison_runs
            (title, subtitle, year, subj_area, open_access_only, category_filter, reference_line, source, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "Publicaciones en todas las áreas — Universidades del Ecuador",
                "Evaluación nacional de 63 universidades e institutos de educación superior",
                "2024",
                "ALL",
                0,
                "University",
                1142.0,
                "workspace_seed (script4.R / plot_pomological.R)",
                now_str,
            ),
        )
        run3_id = cur.lastrowid
        for name, cat, itype, city, count in ECUADOR_UNIVERSITIES_SEED:
            q = f'AFFIL("{name}") AND PUBYEAR = 2024'
            cur.execute(
                """
                INSERT INTO comparison_items
                (run_id, institution_name, category, inst_type, city, total_results, query_used)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (run3_id, name, cat, itype, city, count, q),
            )

    # Seed harvested publication datasets from existing CSVs in workspace
    cur.execute("SELECT COUNT(*) FROM harvest_datasets")
    if cur.fetchone()[0] == 0:
        _seed_csv_datasets(cur)

    conn.commit()
    conn.close()


def _read_university_xlsx_metadata() -> dict:
    xlsx_path = WORKSPACE_DIR / "university_list.xlsx"
    meta = {}
    if not xlsx_path.exists():
        return meta
    try:
        with zipfile.ZipFile(xlsx_path) as z:
            strings = [
                el.text or ""
                for el in ET.fromstring(z.read("xl/sharedStrings.xml")).iter()
                if el.tag.endswith("}t")
            ]
            sheet = ET.fromstring(z.read("xl/worksheets/sheet1.xml"))
            rows = []
            for row in sheet.iter():
                if row.tag.endswith("}row"):
                    r = []
                    for c in row:
                        t = c.attrib.get("t")
                        v = next((ch.text for ch in c if ch.tag.endswith("}v")), None)
                        r.append(strings[int(v)] if (v is not None and t == "s") else (v or ""))
                    rows.append(r)
            for r in rows[1:]:
                if len(r) >= 3 and r[0]:
                    meta[r[0].lower().strip()] = {"type": r[1].strip(), "city": r[2].strip()}
    except Exception:
        pass
    return meta


def _clean_val(val: str) -> str:
    if not val or val.strip().upper() == "NA":
        return ""
    return val.strip()


def _seed_csv_datasets(cur: sqlite3.Cursor) -> None:
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    # 1. INABIO_Publications_2025_Standard.csv
    csv_2025 = WORKSPACE_DIR / "INABIO_Publications_2025_Standard.csv"
    if csv_2025.exists():
        with open(csv_2025, "r", encoding="utf-8", errors="replace") as f:
            reader = list(csv.DictReader(f))
        cur.execute(
            """
            INSERT INTO harvest_datasets
            (title, institution_name, year, view_mode, query_used, total_records, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "INABIO — Publicaciones 2025 (Standard View)",
                "Instituto Nacional de Biodiversidad",
                "2025",
                "STANDARD",
                'AFFIL("Instituto Nacional de Biodiversidad") AND PUBYEAR = 2025',
                len(reader),
                now_str,
            ),
        )
        ds_id = cur.lastrowid
        for row in reader:
            affs = _clean_val(row.get("Affiliations", ""))
            authors = _clean_val(row.get("Authors_List", ""))
            target_auth = authors if ("Biodiversidad" in affs or "INABIO" in affs) else ""
            cur.execute(
                """
                INSERT INTO publications
                (dataset_id, article_name, journal_name, date_publication, issn_isbn,
                 main_knowledge_area, specific_areas, target_authors, authors_list, affiliations, doi)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    ds_id,
                    _clean_val(row.get("Article_Name", "")),
                    _clean_val(row.get("Journal_Name", "")),
                    _clean_val(row.get("Date_Publication", "")),
                    _clean_val(row.get("ISSN_ISBN", "")),
                    _clean_val(row.get("Main_Knowledge_Area", "Journal")),
                    "",
                    target_auth,
                    authors,
                    affs,
                    _clean_val(row.get("DOI", "")),
                ),
            )

    # 2. INABIO_Publications_2024_Final.csv
    csv_2024 = WORKSPACE_DIR / "INABIO_Publications_2024_Final.csv"
    if csv_2024.exists():
        with open(csv_2024, "r", encoding="utf-8", errors="replace") as f:
            reader = list(csv.DictReader(f))
        cur.execute(
            """
            INSERT INTO harvest_datasets
            (title, institution_name, year, view_mode, query_used, total_records, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "INABIO — Publicaciones 2024 (Final Dataset)",
                "Instituto Nacional de Biodiversidad",
                "2024",
                "STANDARD",
                'AFFIL("Instituto Nacional de Biodiversidad") AND PUBYEAR = 2024',
                len(reader),
                now_str,
            ),
        )
        ds_id = cur.lastrowid
        for row in reader:
            affs = _clean_val(row.get("Affiliations", ""))
            authors = _clean_val(row.get("Authors", ""))
            target_auth = authors if ("Biodiversidad" in affs or "INABIO" in affs) else ""
            cur.execute(
                """
                INSERT INTO publications
                (dataset_id, article_name, journal_name, date_publication, issn_isbn,
                 main_knowledge_area, specific_areas, target_authors, authors_list, affiliations, doi)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    ds_id,
                    _clean_val(row.get("Title", "")),
                    _clean_val(row.get("Journal", "")),
                    "2024",
                    "",
                    "Journal",
                    "",
                    target_auth,
                    authors,
                    affs,
                    _clean_val(row.get("DOI", "")),
                ),
            )

