"""
Step 1: Database, Canonical Entity Resolution (Scopus AF-ID & ROR), and Seed Layer
for Scopus Scientific Productivity Studio.

Entities (universities and research institutes) are defined canonically by persistent
identifiers — Scopus Affiliation ID (`afid`) and/or Research Organization Registry ID (`ror_id`) —
rather than fragile institution name strings.
"""

import csv
import gzip
import os
import re
import sqlite3
import unicodedata
import xml.etree.ElementTree as ET
import zipfile
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

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


# Canonical Seed Catalog of 63 Ecuadorian Universities defined by verified ROR / Scopus AF-ID
# Tuple schema:
# (ror_id, afid, acronym, canonical_name, legacy_name, category, inst_type, city, benchmark_2024, search_variants, disambig_city)
ECUADOR_UNIVERSITIES_SEED = [
    ("0198j4566", "60104441", "UDLA", "Universidad de Las Américas", "Universidad de Las Américas", "University", "Private", "Quito", 1142,
     ["Universidad de Las Américas", "Universidad de las Americas"], ""),
    ("01yg1g961", "", "UNAE", "Universidad Nacional de Educación", "Universidad Nacional de Educación", "University", "Public", "Azogues", 881,
     ["Universidad Nacional de Educación", "National University of Education"], "Azogues"),
    ("01r2c3v86", "", "USFQ", "Universidad San Francisco de Quito", "Universidad San Francisco de Quito", "University", "Private", "Quito", 668,
     ["Universidad San Francisco de Quito"], ""),
    ("04qenc566", "", "ESPOL", "Escuela Superior Politécnica del Litoral", "Escuela Superior Politécnica del Litoral", "University", "Public", "Guayaquil", 459,
     ["Escuela Superior Politécnica del Litoral", "ESPOL Polytechnic University"], ""),
    ("01gb99w41", "", "EPN", "Escuela Politécnica Nacional", "Escuela Politécnica Nacional", "University", "Public", "Quito", 422,
     ["Escuela Politécnica Nacional", "National Polytechnic School"], ""),
    ("04dvbth24", "60072064", "UTPL", "Universidad Técnica Particular de Loja", "Universidad Técnica Particular de Loja", "University", "Private", "Loja", 412,
     ["Universidad Técnica Particular de Loja"], ""),
    ("00f11af73", "", "UPS", "Universidad Politécnica Salesiana", "Universidad Politécnica Salesiana", "University", "Private", "Cuenca", 386,
     ["Universidad Politécnica Salesiana", "Politecnica Salesiana University"], ""),
    ("02qztda51", "", "PUCE", "Pontificia Universidad Católica del Ecuador", "Pontificia Universidad Católica del Ecuador", "University", "Private", "Quito", 382,
     ["Pontificia Universidad Católica del Ecuador", "Pontifical Catholic University of Ecuador"], ""),
    ("00cgjqd45", "", "UNIANDES", "Universidad Regional Autónoma de Los Andes", "Universidad Regional Autónoma de los Andes", "University", "Private", "Ambato", 371,
     ["Universidad Regional Autónoma de Los Andes"], ""),
    ("02zyw2q61", "", "ESPOCH", "Escuela Superior Politécnica de Chimborazo", "Escuela Superior Politécnica de Chimborazo", "University", "Public", "Riobamba", 336,
     ["Escuela Superior Politécnica de Chimborazo", "Escuela Superior Politécnica del Chimborazo"], ""),
    ("05j136930", "", "ESPE", "Universidad de las Fuerzas Armadas ESPE", "Universidad de las Fuerzas Armadas", "University", "Public", "Sangolquí", 318,
     ["Universidad de las Fuerzas Armadas ESPE", "Universidad de las Fuerzas Armadas", "Escuela Politécnica del Ejército"], ""),
    ("02qgahb88", "", "UTM", "Universidad Técnica de Manabí", "Universidad Técnica de Manabí", "University", "Public", "Portoviejo", 268,
     ["Universidad Técnica de Manabí"], ""),
    ("048nctr92", "", "UTA", "Universidad Técnica de Ambato", "Universidad Técnica de Ambato", "University", "Public", "Ambato", 261,
     ["Universidad Técnica de Ambato"], ""),
    ("0077ex633", "", "UMET", "Universidad Metropolitana", "Universidad Metropolitana", "University", "Private", "Guayaquil", 254,
     ["Universidad Metropolitana"], ""),
    ("059wmd288", "", "UNACH", "Universidad Nacional de Chimborazo", "Universidad Nacional de Chimborazo", "University", "Public", "Riobamba", 238,
     ["Universidad Nacional de Chimborazo"], ""),
    ("04r23zn56", "", "UCUENCA", "Universidad de Cuenca", "Universidad de Cuenca", "University", "Public", "Cuenca", 236,
     ["Universidad de Cuenca", "University of Cuenca"], ""),
    ("010n0x685", "", "UCE", "Universidad Central del Ecuador", "Universidad Central del Ecuador", "University", "Public", "Quito", 234,
     ["Universidad Central del Ecuador", "Central University of Ecuador"], ""),
    ("047kyg834", "", "UG", "Universidad de Guayaquil", "Universidad de Guayaquil", "University", "Public", "Guayaquil", 198,
     ["Universidad de Guayaquil", "University of Guayaquil"], ""),
    ("037xrmj59", "", "UDA", "Universidad del Azuay", "Universidad del Azuay", "University", "Private", "Cuenca", 162,
     ["Universidad del Azuay", "University of Azuay"], ""),
    ("00dmdt028", "", "UTE", "Universidad UTE", "Universidad UTE", "University", "Private", "Quito", 148,
     ["Universidad UTE", "Universidad Tecnológica Equinoccial", "UTE University"], ""),
    ("00gd7ns03", "", "UNEMI", "Universidad Estatal de Milagro", "Universidad Estatal de Milagro", "University", "Public", "Milagro", 145,
     ["Universidad Estatal de Milagro", "State University of Milagro"], ""),
    ("04xf2rc74", "", "UIDE", "Universidad Internacional del Ecuador", "Universidad Internacional del Ecuador", "University", "Private", "Quito", 141,
     ["Universidad Internacional del Ecuador"], ""),
    ("0036b6n81", "", "UCACUE", "Universidad Católica de Cuenca", "Universidad Católica de Cuenca", "University", "Private", "Cuenca", 137,
     ["Universidad Católica de Cuenca"], ""),
    ("02nn67a65", "", "UTI", "Universidad Indoamérica", "Universidad Tecnológica Indoamérica", "University", "Private", "Ambato", 116,
     ["Universidad Tecnológica Indoamérica", "Universidad Indoamérica"], ""),
    ("004jbx603", "", "UTC", "Universidad Técnica de Cotopaxi", "Universidad Técnica de Cotopaxi", "University", "Public", "Latacunga", 112,
     ["Universidad Técnica de Cotopaxi"], ""),
    ("03f0t8b71", "", "UTN", "Universidad Técnica del Norte", "Universidad Técnica del Norte", "University", "Public", "Ibarra", 104,
     ["Universidad Técnica del Norte"], ""),
    ("031aa0x95", "", "UBE", "Universidad Bolivariana del Ecuador", "Universidad Bolivariana del Ecuador", "University", "Private", "Durán", 96,
     ["Universidad Bolivariana del Ecuador"], ""),
    ("030snpp57", "", "UCSG", "Universidad Católica de Santiago de Guayaquil", "Universidad Católica de Santiago de Guayaquil", "University", "Private", "Guayaquil", 94,
     ["Universidad Católica de Santiago de Guayaquil", "Catholic University of Santiago de Guayaquil"], ""),
    ("02rz0r794", "", "FLACSO", "Facultad Latinoamericana de Ciencias Sociales Ecuador", "Facultad Latinoamericana de Ciencias Sociales", "University", "Public", "Quito", 91,
     ["Facultad Latinoamericana de Ciencias Sociales", "FLACSO Ecuador", "Latin American Faculty of Social Sciences"], ""),
    ("01k410495", "", "UPSE", "Universidad Estatal Península de Santa Elena", "Universidad Estatal Península de Santa Elena", "University", "Public", "La Libertad", 86,
     ["Universidad Estatal Península de Santa Elena"], ""),
    ("05qrwjj27", "", "UTEQ", "Universidad Técnica Estatal de Quevedo", "Universidad Técnica Estatal de Quevedo", "University", "Public", "Quevedo", 84,
     ["Universidad Técnica Estatal de Quevedo"], ""),
    ("03a5x6z77", "", "UNL", "Universidad Nacional de Loja", "Universidad Nacional de Loja", "University", "Public", "Loja", 82,
     ["Universidad Nacional de Loja"], ""),
    ("05xedqd83", "", "IKIAM", "Universidad Regional Amazónica Ikiam", "Universidad Regional Amazónica Ikiam", "University", "Public", "Tena", 71,
     ["Universidad Regional Amazónica Ikiam", "Amazon Regional University Ikiam"], ""),
    ("029ss0s83", "", "UEA", "Universidad Estatal Amazónica", "Universidad Estatal Amazónica", "University", "Public", "Puyo", 64,
     ["Universidad Estatal Amazónica"], ""),
    ("01m8gvd94", "", "ULEAM", "Universidad Laica Eloy Alfaro de Manabí", "Universidad Laica Eloy Alfaro de Manabí", "University", "Public", "Manta", 58,
     ["Universidad Laica Eloy Alfaro de Manabí"], ""),
    ("036zk8k10", "", "UTMACH", "Universidad Técnica de Machala", "Universidad Técnica de Machala", "University", "Public", "Machala", 46,
     ["Universidad Técnica de Machala"], ""),
    ("01wea3g49", "", "ESPAM", "Escuela Superior Politécnica Agropecuaria de Manabí", "Escuela Superior Politécnica Agropecuaria de Manabí", "University", "Public", "Calceta", 39,
     ["Escuela Superior Politécnica Agropecuaria de Manabí", "Escuela Superior Politécnica Agropecuaria de Manabí Manuel Félix López"], ""),
    ("043psk135", "", "UASB-E", "Universidad Andina Simón Bolívar, Sede Ecuador", "Universidad Andina Simón Bolívar", "University", "Public", "Quito", 38,
     ["Universidad Andina Simón Bolívar", "Andean Simón Bolívar University"], ""),
    ("03z4qet58", "", "UAE", "Universidad Agraria del Ecuador", "Universidad Agraria del Ecuador", "University", "Public", "Guayaquil", 37,
     ["Universidad Agraria del Ecuador"], ""),
    ("05pnzjf85", "", "UNESUM", "Universidad Estatal del Sur de Manabí", "Universidad Estatal del Sur de Manabí", "University", "Public", "Jipijapa", 35,
     ["Universidad Estatal del Sur de Manabí"], ""),
    ("005cgg117", "", "UEB", "Universidad Estatal de Bolívar", "Universidad Estatal de Bolívar", "University", "Public", "Guaranda", 29,
     ["Universidad Estatal de Bolívar"], ""),
    ("0570zmv60", "", "UTB", "Universidad Técnica de Babahoyo", "Universidad Técnica de Babahoyo", "University", "Public", "Babahoyo", 27,
     ["Universidad Técnica de Babahoyo"], ""),
    ("029zzvq50", "", "UISRAEL", "Universidad Tecnológica Israel", "Universidad Tecnológica Israel", "University", "Private", "Quito", 21,
     ["Universidad Tecnológica Israel", "Universidad Israel"], ""),
    ("04pe1sa24", "", "ECOTEC", "Universidad Tecnológica ECOTEC", "Universidad Tecnológica ECOTEC", "University", "Private", "Samborondón", 19,
     ["Universidad Tecnológica ECOTEC", "Universidad Ecotec", "Ecotec University"], ""),
    ("04msd0t92", "", "UPEC", "Universidad Politécnica Estatal del Carchi", "Universidad Politécnica Estatal del Carchi", "University", "Public", "Tulcán", 18,
     ["Universidad Politécnica Estatal del Carchi"], ""),
    ("011g3me54", "", "IAEN", "Instituto de Altos Estudios Nacionales", "Instituto de Altos Estudios Nacionales", "University", "Public", "Quito", 17,
     ["Instituto de Altos Estudios Nacionales"], ""),
    ("056srs126", "", "UTEG", "Universidad Tecnológica Empresarial de Guayaquil", "Universidad Tecnológica Empresarial de Guayaquil", "University", "Private", "Guayaquil", 15,
     ["Universidad Tecnológica Empresarial de Guayaquil"], ""),
    ("016drwn73", "", "UARTES", "Universidad de las Artes", "Universidad de las Artes", "University", "Public", "Guayaquil", 14,
     ["Universidad de las Artes"], ""),
    ("04jjswc10", "60105012", "YACHAY", "Universidad Yachay Tech", "Universidad de Investigación de Tecnología Experimental Yachay", "University", "Public", "Urcuquí", 14,
     ["Universidad Yachay Tech", "Universidad de Investigación de Tecnología Experimental Yachay", "Yachay University"], ""),
    ("02sqp5835", "", "UDLH", "Universidad de los Hemisferios", "Universidad de los Hemisferios", "University", "Private", "Quito", 13,
     ["Universidad de los Hemisferios", "Universidad Los Hemisferios"], ""),
    ("05164ka66", "", "UDET", "Universidad de Especialidades Turísticas", "Universidad de Especialidades Turísticas", "University", "Private", "Quito", 12,
     ["Universidad de Especialidades Turísticas"], ""),
    ("011bd9v54", "", "UCG", "Universidad Casa Grande", "Universidad Casa Grande", "University", "Private", "Guayaquil", 11,
     ["Universidad Casa Grande"], ""),
    ("03ejpjn40", "", "UINPIAW", "Universidad Intercultural de las Nacionalidades y Pueblos Indígenas Amawtay Wasi", "Universidad Intercultural de las Nacionalidades Y Pueblos Indígenas Amawtay Wasi", "University", "Public", "Quito", 10,
     ["Universidad Intercultural de las Nacionalidades y Pueblos Indígenas Amawtay Wasi", "Universidad Amawtay Wasi"], ""),
    ("010w4rs44", "", "UTELVT", "Universidad Técnica Luis Vargas Torres de Esmeraldas", "Universidad Técnica Luis Vargas Torres de Esmeraldas", "University", "Public", "Esmeraldas", 9,
     ["Universidad Técnica Luis Vargas Torres de Esmeraldas", "Universidad Técnica Luis Vargas Torres"], ""),
    ("00x6twa51", "", "UO", "Universidad de Otavalo", "Universidad de Otavalo", "University", "Private", "Otavalo", 8,
     ["Universidad de Otavalo"], ""),
    ("038bgqv50", "", "ULVR", "Universidad Laica Vicente Rocafuerte de Guayaquil", "Universidad Laica Vicente Rocafuerte de Guayaquil", "University", "Private", "Guayaquil", 7,
     ["Universidad Laica Vicente Rocafuerte de Guayaquil"], ""),
    ("03693e022", "", "UNIBE", "Universidad Iberoamericana del Ecuador", "Universidad Iberoamericana del Ecuador", "University", "Private", "Quito", 6,
     ["Universidad Iberoamericana del Ecuador"], ""),
    ("0139vf833", "", "USGP", "Universidad San Gregorio de Portoviejo", "Universidad Particular San Gregorio de Portoviejo", "University", "Private", "Portoviejo", 5,
     ["Universidad San Gregorio de Portoviejo", "Universidad Particular San Gregorio de Portoviejo"], ""),
    ("00nk5y742", "", "UISEK", "Universidad Internacional SEK", "Universidad Particular Internacional SEK", "University", "Private", "Quito", 4,
     ["Universidad Internacional SEK", "Universidad Particular Internacional SEK"], ""),
    ("02kv83127", "", "UDR", "Universidad del Río", "Universidad del Río", "University", "Private", "Guayaquil", 3,
     ["Universidad del Río"], ""),
    ("00b210x50", "", "UEES", "Universidad Espíritu Santo", "Universidad Particular de Especialidades Espíritu Santo", "University", "Private", "Samborondón", 2,
     ["Universidad Espíritu Santo", "Universidad de Especialidades Espíritu Santo", "Universidad Particular de Especialidades Espíritu Santo"], ""),
    ("00eg5dk50", "", "UPACIFICO", "Universidad Del Pacífico Ecuador", "Universidad del Pacífico Escuela de Negocios", "University", "Private", "Guayaquil", 1,
     ["Universidad del Pacífico", "Universidad Del Pacífico Ecuador"], ""),
    ("", "", "USECIPOL", "Universidad de Seguridad Ciudadana y Ciencias Policiales", "Universidad de Seguridad Ciudadana y Ciencias Policiales", "University", "Public", "Quito", 0,
     ["Universidad de Seguridad Ciudadana y Ciencias Policiales"], ""),
]

# Canonical Seed Catalog of 7 Ecuadorian Public Research Institutes (including IPIAP)
PUBLIC_RESEARCH_INSTITUTES_SEED = [
    ("02veev176", "", "INABIO", "Instituto Nacional de Biodiversidad", "Instituto Nacional de Biodiversidad", "Research Institute", "Public", "Quito", 88,
     ["Instituto Nacional de Biodiversidad", "National Institute of Biodiversity"], ""),
    ("01vep7794", "", "INIAP", "Instituto Nacional de Investigaciones Agropecuarias", "Instituto Nacional de Investigaciones Agropecuarias", "Research Institute", "Public", "Quito", 44,
     ["Instituto Nacional de Investigaciones Agropecuarias"], ""),
    ("00zma5460", "", "INSPI", "Instituto Nacional de Investigación en Salud Pública", "Instituto Nacional de Investigación en Salud Pública", "Research Institute", "Public", "Guayaquil", 23,
     ["Instituto Nacional de Investigación en Salud Pública", "Instituto Nacional de Investigación en Salud Pública Dr. Leopoldo Izquieta Pérez"], ""),
    ("03rrkbt66", "", "IIGE", "Instituto de Investigación Geológico y Energético", "Instituto de Investigación Geológico y Energético", "Research Institute", "Public", "Quito", 17,
     ["Instituto de Investigación Geológico y Energético"], ""),
    ("027q5ca10", "", "INPC", "Instituto Nacional de Patrimonio Cultural", "Instituto Nacional de Patrimonio Cultural", "Research Institute", "Public", "Quito", 5,
     ["Instituto Nacional de Patrimonio Cultural"], ""),
    ("", "", "INAMHI", "Instituto Nacional de Meteorología e Hidrología", "Instituto Nacional de Meteorología e Hidrología", "Research Institute", "Public", "Quito", 2,
     ["Instituto Nacional de Meteorología e Hidrología"], ""),
    ("", "", "IPIAP", "Instituto Público de Investigación de Acuicultura y Pesca", "Instituto Público de Investigación de Acuicultura y Pesca", "Research Institute", "Public", "Guayaquil", 12,
     ["Instituto Público de Investigación de Acuicultura y Pesca", "Public Institute of Aquaculture and Fisheries Research", "Instituto Nacional de Pesca"], ""),
]

# AGRI benchmark group defined strictly by canonical ROR IDs (no institution names)
AGRI_COMPARISON_SEED = [
    ("0198j4566", 197),  # UDLA
    ("01r2c3v86", 119),  # USFQ
    ("02qztda51", 89),   # PUCE
    ("02veev176", 86),   # INABIO
    ("05j136930", 30),   # ESPE
    ("05xedqd83", 26),   # IKIAM
]


def normalize_text(text: str) -> str:
    """Normalize accents, case, and punctuation for deterministic comparison."""
    if not text:
        return ""
    s = unicodedata.normalize("NFD", str(text).lower().strip())
    s = "".join(c for c in s if unicodedata.category(c) != "Mn")
    s = re.sub(r"[^a-z0-9]+", " ", s)
    return " ".join(s.split())


def normalize_ror_id(raw: Any) -> str:
    """Extract and validate a canonical 9-character ROR identifier (e.g. '0198j4566')."""
    if not raw:
        return ""
    s = str(raw).strip().lower()
    s = re.sub(r"^https?://(?:www\.)?ror\.org/", "", s)
    s = re.sub(r"^ror\.org/", "", s)
    s = re.sub(r"^ror:", "", s)
    m = re.search(r"\b(0[a-z0-9]{8})\b", s)
    return m.group(1) if m else ""


def normalize_afids(raw: Any) -> list[str]:
    """Extract ordered, deduplicated numeric Scopus Affiliation IDs (8-10 digits)."""
    if not raw:
        return []
    if isinstance(raw, (list, tuple, set)):
        text = " ".join(str(x) for x in raw)
    else:
        text = str(raw)
    found = re.findall(r"\b(\d{8,10})\b", text)
    seen = set()
    out = []
    for fid in found:
        if fid not in seen:
            seen.add(fid)
            out.append(fid)
    return out


def format_afids(raw: Any) -> str:
    """Serialize normalized Scopus AF-IDs as '; '-separated string."""
    return "; ".join(normalize_afids(raw))


def compute_entity_uid(ror_id: str = "", afid: str = "", fallback_code: str = "") -> str:
    """Build a canonical, persistent identifier key for an institutional entity."""
    rid = normalize_ror_id(ror_id)
    if rid:
        return f"ror:{rid}"
    afids = normalize_afids(afid)
    if afids:
        return f"scopus:{afids[0]}"
    slug = re.sub(r"[^a-z0-9]+", "-", normalize_text(fallback_code)).strip("-") or "entity"
    return f"ec:{slug}"


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


def _build_seed_lookup() -> dict[str, dict]:
    """Create lookup maps for canonical seed entities by ROR, AF-ID, acronym, and legacy/canonical names."""
    xlsx_meta = _read_university_xlsx_metadata()
    by_key = {}
    all_seed = list(ECUADOR_UNIVERSITIES_SEED) + list(PUBLIC_RESEARCH_INSTITUTES_SEED)
    for ror_id, afid, acr, cname, lname, cat, itype, city, bench, variants, disambig_city in all_seed:
        for nm_check in (cname.lower().strip(), lname.lower().strip()):
            if nm_check in xlsx_meta:
                itype = xlsx_meta[nm_check].get("type", itype) or itype
                city = xlsx_meta[nm_check].get("city", city) or city
                break
        uid = compute_entity_uid(ror_id=ror_id, afid=afid, fallback_code=acr or cname)
        rec = {
            "entity_uid": uid,
            "ror_id": normalize_ror_id(ror_id),
            "afid": format_afids(afid),
            "afid_status": "verified" if normalize_afids(afid) else "pending",
            "acronym": acr,
            "name": cname,
            "legacy_name": lname,
            "category": cat,
            "inst_type": itype,
            "city": city,
            "country": "Ecuador",
            "disambig_city": disambig_city,
            "aliases": "; ".join(variants),
            "benchmark_2024": bench,
        }
        by_key[f"uid:{uid}"] = rec
        if rec["ror_id"]:
            by_key[f"ror:{rec['ror_id']}"] = rec
        for fid in normalize_afids(afid):
            by_key[f"afid:{fid}"] = rec
        by_key[f"acr:{acr.upper()}"] = rec
        by_key[f"name:{normalize_text(cname)}"] = rec
        by_key[f"name:{normalize_text(lname)}"] = rec
        for v in variants:
            by_key.setdefault(f"name:{normalize_text(v)}", rec)
    return by_key


def find_institution(conn: sqlite3.Connection, ref: Any) -> Optional[dict]:
    """
    Resolve an institutional entity primarily by identifier:
    - integer `id`
    - `entity_uid` ('ror:0198j4566', 'scopus:60104441', 'ec:ipiap')
    - Scopus `afid` ('60104441', 'AF-ID(60104441)')
    - `ror_id` ('0198j4566', 'https://ror.org/0198j4566')
    - `acronym` ('UDLA', 'INABIO', 'IPIAP')
    - legacy name / alias fallback for backwards compatibility.
    """
    if ref is None:
        return None

    if isinstance(ref, dict):
        for k in ("entity_uid", "afid", "ror_id", "id", "acronym", "name"):
            if ref.get(k):
                hit = find_institution(conn, ref[k])
                if hit:
                    return hit
        return None

    if isinstance(ref, int) or (isinstance(ref, str) and ref.strip().isdigit() and len(ref.strip()) <= 6):
        row = conn.execute("SELECT * FROM institutions WHERE id = ?", (int(ref),)).fetchone()
        return dict(row) if row else None

    s = str(ref).strip()
    if not s:
        return None

    # 1. Exact entity_uid
    row = conn.execute("SELECT * FROM institutions WHERE LOWER(entity_uid) = ?", (s.lower(),)).fetchone()
    if row:
        return dict(row)

    # 2. ROR ID
    rid = normalize_ror_id(s)
    if rid:
        row = conn.execute("SELECT * FROM institutions WHERE LOWER(ror_id) = ?", (rid,)).fetchone()
        if row:
            return dict(row)

    # 3. Scopus AF-ID
    req_afids = set(normalize_afids(s))
    if req_afids:
        all_rows = conn.execute("SELECT * FROM institutions WHERE afid != ''").fetchall()
        for r in all_rows:
            if req_afids.intersection(normalize_afids(r["afid"])):
                return dict(r)

    # 4. Exact acronym
    if len(s) <= 12 and re.match(r"^[A-Za-z0-9._-]+$", s):
        row = conn.execute("SELECT * FROM institutions WHERE UPPER(acronym) = ?", (s.upper(),)).fetchone()
        if row:
            return dict(row)

    # 5. Normalized name / aliases fallback (for legacy records)
    target_norm = normalize_text(s)
    if target_norm:
        all_rows = conn.execute("SELECT * FROM institutions").fetchall()
        for r in all_rows:
            if normalize_text(r["name"]) == target_norm:
                return dict(r)
        seed_map = _build_seed_lookup()
        seed_hit = seed_map.get(f"name:{target_norm}")
        if seed_hit:
            row = conn.execute(
                "SELECT * FROM institutions WHERE entity_uid = ?", (seed_hit["entity_uid"],)
            ).fetchone()
            if row:
                return dict(row)
        for r in all_rows:
            aliases = [normalize_text(a) for a in (r["aliases"] or "").split(";") if a.strip()]
            if target_norm in aliases:
                return dict(r)

    return None


def upsert_institution(conn: sqlite3.Connection, data: dict, allow_provisional: bool = False) -> dict:
    """
    Insert or update an entity keyed by its persistent identifier (`ror_id` or `afid`).
    Raises ValueError if neither `ror_id` nor `afid` is provided (unless allow_provisional=True).
    """
    inst_id = data.get("id")
    ror_id = normalize_ror_id(data.get("ror_id", ""))
    afid = format_afids(data.get("afid", ""))

    if not ror_id and not afid and not allow_provisional:
        raise ValueError(
            "Se requiere al menos un identificador persistente: Scopus AF-ID (ej. 60104441) o ROR ID (ej. 0198j4566)."
        )

    existing = None
    if inst_id:
        existing = find_institution(conn, int(inst_id))
    if not existing and ror_id:
        existing = find_institution(conn, ror_id)
    if not existing and afid:
        for fid in normalize_afids(afid):
            existing = find_institution(conn, fid)
            if existing:
                break
    if not existing and data.get("entity_uid"):
        existing = find_institution(conn, data["entity_uid"])

    acronym = str(data.get("acronym", "") or (existing["acronym"] if existing else "")).strip()
    name = str(data.get("name", "") or (existing["name"] if existing else "")).strip()
    if not name:
        if afid:
            name = f"Entidad Scopus AF-ID:{normalize_afids(afid)[0]}"
        elif ror_id:
            name = f"Entidad ROR:{ror_id}"
        else:
            name = acronym or "Entidad sin etiqueta"

    category = str(data.get("category") or (existing["category"] if existing else "University")).strip()
    inst_type = str(data.get("inst_type") or (existing["inst_type"] if existing else "Public")).strip()
    city = str(data.get("city") if data.get("city") is not None else (existing["city"] if existing else "")).strip()
    country = str(data.get("country") or (existing["country"] if existing else "Ecuador")).strip()
    disambig_city = str(
        data.get("disambig_city")
        if data.get("disambig_city") is not None
        else (existing["disambig_city"] if existing else "")
    ).strip()
    aliases = str(
        data.get("aliases") if data.get("aliases") is not None else (existing["aliases"] if existing else "")
    ).strip()

    merged_ror = ror_id or (existing["ror_id"] if existing else "")
    merged_afid = afid if data.get("afid") is not None else (existing["afid"] if existing else "")
    afid_status = data.get("afid_status") or (
        "verified" if normalize_afids(merged_afid) else (existing["afid_status"] if existing else "pending")
    )

    entity_uid = compute_entity_uid(
        ror_id=merged_ror,
        afid=merged_afid,
        fallback_code=acronym or name,
    )

    cur = conn.cursor()
    if existing:
        old_uid = existing["entity_uid"]
        cur.execute(
            """
            UPDATE institutions
            SET entity_uid = ?, ror_id = ?, afid = ?, afid_status = ?, acronym = ?,
                name = ?, category = ?, inst_type = ?, city = ?, country = ?,
                disambig_city = ?, aliases = ?, active = 1
            WHERE id = ?
            """,
            (
                entity_uid,
                merged_ror,
                merged_afid,
                afid_status,
                acronym,
                name,
                category,
                inst_type,
                city,
                country,
                disambig_city,
                aliases,
                existing["id"],
            ),
        )
        # Keep linked comparison_items and harvest_datasets consistent
        cur.execute(
            """
            UPDATE comparison_items
            SET entity_uid = ?, ror_id = ?, afid = ?, acronym = ?, institution_name = ?
            WHERE entity_uid = ?
            """,
            (entity_uid, merged_ror, merged_afid, acronym, name, old_uid),
        )
        cur.execute(
            """
            UPDATE harvest_datasets
            SET entity_uid = ?, ror_id = ?, afid = ?, acronym = ?, institution_name = ?
            WHERE entity_uid = ?
            """,
            (entity_uid, merged_ror, merged_afid, acronym, name, old_uid),
        )
        target_id = existing["id"]
    else:
        cur.execute(
            """
            INSERT INTO institutions
            (entity_uid, ror_id, afid, afid_status, acronym, name, category, inst_type,
             city, country, disambig_city, aliases, active)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1)
            """,
            (
                entity_uid,
                merged_ror,
                merged_afid,
                afid_status,
                acronym,
                name,
                category,
                inst_type,
                city,
                country,
                disambig_city,
                aliases,
            ),
        )
        target_id = cur.lastrowid

    conn.commit()
    row = conn.execute("SELECT * FROM institutions WHERE id = ?", (target_id,)).fetchone()
    return dict(row)


def _ensure_column(cur: sqlite3.Cursor, table: str, column: str, col_def: str) -> None:
    cols = {r[1] for r in cur.execute(f"PRAGMA table_info({table})").fetchall()}
    if column not in cols:
        cur.execute(f"ALTER TABLE {table} ADD COLUMN {column} {col_def}")


def _migrate_schema_and_entities(conn: sqlite3.Connection) -> None:
    """
    Idempotently migrate existing databases from name-keyed institutions to
    identifier-keyed (`entity_uid` / `ror_id` / `afid`) entities, backfill
    comparison_items and harvest_datasets, and ensure all 70 Ecuadorian seed
    entities (including IPIAP) are registered.
    """
    cur = conn.cursor()
    inst_cols = {r[1] for r in cur.execute("PRAGMA table_info(institutions)").fetchall()}
    seed_lookup = _build_seed_lookup()

    if "entity_uid" not in inst_cols:
        old_rows = [dict(r) for r in cur.execute("SELECT * FROM institutions ORDER BY id ASC").fetchall()]
        cur.execute(
            """
            CREATE TABLE institutions_v2 (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                entity_uid TEXT UNIQUE NOT NULL,
                ror_id TEXT DEFAULT '',
                afid TEXT DEFAULT '',
                afid_status TEXT DEFAULT 'pending',
                acronym TEXT DEFAULT '',
                name TEXT NOT NULL,
                category TEXT NOT NULL DEFAULT 'University',
                inst_type TEXT NOT NULL DEFAULT 'Public',
                city TEXT DEFAULT '',
                country TEXT DEFAULT 'Ecuador',
                disambig_city TEXT DEFAULT '',
                aliases TEXT DEFAULT '',
                active INTEGER NOT NULL DEFAULT 1
            )
            """
        )
        used_uids = set()
        for old in old_rows:
            old_name = old.get("name", "")
            old_afid = format_afids(old.get("afid", ""))
            old_ror = normalize_ror_id(old.get("aliases", ""))

            matched = None
            if old_ror and f"ror:{old_ror}" in seed_lookup:
                matched = seed_lookup[f"ror:{old_ror}"]
            if not matched and old_afid:
                for fid in normalize_afids(old_afid):
                    if f"afid:{fid}" in seed_lookup:
                        matched = seed_lookup[f"afid:{fid}"]
                        break
            if not matched:
                matched = seed_lookup.get(f"name:{normalize_text(old_name)}")

            if matched:
                ror_id = matched["ror_id"]
                afid = format_afids(f"{old_afid}; {matched['afid']}")
                afid_status = "verified" if normalize_afids(afid) else "pending"
                acronym = matched["acronym"]
                name = matched["name"]
                category = matched["category"]
                inst_type = matched["inst_type"]
                city = old.get("city") or matched["city"]
                country = matched["country"]
                disambig_city = matched["disambig_city"]
                aliases = matched["aliases"]
                uid = compute_entity_uid(ror_id=ror_id, afid=afid, fallback_code=acronym or name)
            else:
                ror_id = old_ror
                afid = old_afid
                afid_status = "verified" if normalize_afids(afid) else "pending"
                acronym = ""
                name = old_name
                category = old.get("category", "University")
                inst_type = old.get("inst_type", "Public")
                city = old.get("city", "")
                country = "Ecuador"
                disambig_city = ""
                aliases = old.get("aliases", "")
                uid = compute_entity_uid(ror_id=ror_id, afid=afid, fallback_code=old_name)

            if uid in used_uids:
                uid = f"{uid}-{old['id']}"
            used_uids.add(uid)

            cur.execute(
                """
                INSERT INTO institutions_v2
                (id, entity_uid, ror_id, afid, afid_status, acronym, name, category, inst_type,
                 city, country, disambig_city, aliases, active)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    old["id"],
                    uid,
                    ror_id,
                    afid,
                    afid_status,
                    acronym,
                    name,
                    category,
                    inst_type,
                    city,
                    country,
                    disambig_city,
                    aliases,
                    old.get("active", 1),
                ),
            )

        cur.execute("DROP TABLE institutions")
        cur.execute("ALTER TABLE institutions_v2 RENAME TO institutions")

    cur.execute("CREATE INDEX IF NOT EXISTS idx_institutions_ror ON institutions(ror_id)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_institutions_afid ON institutions(afid)")

    # Ensure all 70 canonical Ecuadorian seed entities (including IPIAP) exist
    all_seed_tuples = list(ECUADOR_UNIVERSITIES_SEED) + list(PUBLIC_RESEARCH_INSTITUTES_SEED)
    for ror_id, afid, acr, cname, _lname, cat, itype, city, _bench, variants, disambig_city in all_seed_tuples:
        uid = compute_entity_uid(ror_id=ror_id, afid=afid, fallback_code=acr or cname)
        exists = None
        if ror_id:
            exists = cur.execute("SELECT id, afid FROM institutions WHERE ror_id = ?", (ror_id,)).fetchone()
        if not exists and afid:
            exists = cur.execute("SELECT id, afid FROM institutions WHERE afid LIKE ?", (f"%{afid}%",)).fetchone()
        if not exists:
            exists = cur.execute(
                "SELECT id, afid FROM institutions WHERE entity_uid = ? OR UPPER(acronym) = ?",
                (uid, acr.upper()),
            ).fetchone()
        if not exists:
            cur.execute(
                """
                INSERT INTO institutions
                (entity_uid, ror_id, afid, afid_status, acronym, name, category, inst_type,
                 city, country, disambig_city, aliases, active)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'Ecuador', ?, ?, 1)
                """,
                (
                    uid,
                    normalize_ror_id(ror_id),
                    format_afids(afid),
                    "verified" if normalize_afids(afid) else "pending",
                    acr,
                    cname,
                    cat,
                    itype,
                    city,
                    disambig_city,
                    "; ".join(variants),
                ),
            )

    # Upgrade comparison_items and harvest_datasets with persistent entity identifier columns
    for tbl in ("comparison_items", "harvest_datasets"):
        _ensure_column(cur, tbl, "entity_uid", "TEXT DEFAULT ''")
        _ensure_column(cur, tbl, "ror_id", "TEXT DEFAULT ''")
        _ensure_column(cur, tbl, "afid", "TEXT DEFAULT ''")
        _ensure_column(cur, tbl, "acronym", "TEXT DEFAULT ''")

    conn.commit()

    # Backfill identifier metadata on comparison_items and harvest_datasets
    for tbl in ("comparison_items", "harvest_datasets"):
        missing_rows = cur.execute(
            f"SELECT id, institution_name FROM {tbl} WHERE entity_uid IS NULL OR entity_uid = ''"
        ).fetchall()
        for mr in missing_rows:
            inst = find_institution(conn, mr["institution_name"])
            if inst:
                cur.execute(
                    f"""
                    UPDATE {tbl}
                    SET entity_uid = ?, ror_id = ?, afid = ?, acronym = ?, institution_name = ?
                    WHERE id = ?
                    """,
                    (
                        inst["entity_uid"],
                        inst["ror_id"],
                        inst["afid"],
                        inst["acronym"],
                        inst["name"],
                        mr["id"],
                    ),
                )
    conn.commit()


def _seed_default_query(rec: dict, year: str, subj: str = "ALL") -> str:
    afids = normalize_afids(rec.get("afid", ""))
    if afids:
        aff = f"AF-ID({afids[0]})" if len(afids) == 1 else "(" + " OR ".join(f"AF-ID({x})" for x in afids) + ")"
    else:
        aff = f'AFFIL("{rec["name"]}") AND AFFILCOUNTRY(Ecuador)'
        if rec.get("disambig_city"):
            aff = f'({aff} AND AFFIL("{rec["disambig_city"]}"))'
    parts = [aff]
    if subj and subj != "ALL":
        parts.append(f"SUBJAREA({subj})")
    parts.append(f"PUBYEAR = {year}")
    return " AND ".join(parts)


def init_db() -> None:
    """Create/migrate tables and seed canonical entities, subject areas, and benchmark runs."""
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
            entity_uid TEXT UNIQUE NOT NULL,
            ror_id TEXT DEFAULT '',
            afid TEXT DEFAULT '',
            afid_status TEXT DEFAULT 'pending',
            acronym TEXT DEFAULT '',
            name TEXT NOT NULL,
            category TEXT NOT NULL DEFAULT 'University',
            inst_type TEXT NOT NULL DEFAULT 'Public',
            city TEXT DEFAULT '',
            country TEXT DEFAULT 'Ecuador',
            disambig_city TEXT DEFAULT '',
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
            entity_uid TEXT DEFAULT '',
            ror_id TEXT DEFAULT '',
            afid TEXT DEFAULT '',
            acronym TEXT DEFAULT '',
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
            entity_uid TEXT DEFAULT '',
            ror_id TEXT DEFAULT '',
            afid TEXT DEFAULT '',
            acronym TEXT DEFAULT '',
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

    # Migrate and seed all 70 canonical institutions (63 universities + 7 public research institutes)
    _migrate_schema_and_entities(conn)

    # Seed initial comparison runs if empty
    cur.execute("SELECT COUNT(*) FROM comparison_runs")
    if cur.fetchone()[0] == 0:
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        seed_lookup = _build_seed_lookup()

        # 1) 7 Public Research Institutes (including IPIAP)
        cur.execute(
            """
            INSERT INTO comparison_runs
            (title, subtitle, year, subj_area, open_access_only, category_filter, reference_line, source, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "Publicaciones en todas las áreas — Institutos Públicos",
                "Comparativa de 7 institutos públicos de investigación del Ecuador (ROR / Scopus AF-ID)",
                "2025",
                "ALL",
                0,
                "Research Institute",
                65.0,
                "workspace_seed (canonical ROR / AF-ID)",
                now_str,
            ),
        )
        run1_id = cur.lastrowid
        for ror_id, afid, acr, cname, _lname, cat, itype, city, count, _variants, _dcity in PUBLIC_RESEARCH_INSTITUTES_SEED:
            uid = compute_entity_uid(ror_id=ror_id, afid=afid, fallback_code=acr)
            rec = seed_lookup[f"uid:{uid}"]
            q = _seed_default_query(rec, "2025", "ALL")
            cur.execute(
                """
                INSERT INTO comparison_items
                (run_id, entity_uid, ror_id, afid, acronym, institution_name, category, inst_type, city, total_results, query_used)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (run1_id, rec["entity_uid"], rec["ror_id"], rec["afid"], acr, cname, cat, itype, city, count, q),
            )

        # 2) AGRI Comparison keyed by ROR ID
        cur.execute(
            """
            INSERT INTO comparison_runs
            (title, subtitle, year, subj_area, open_access_only, category_filter, reference_line, source, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "Publicaciones en Agricultura y Ciencias Biológicas (AGRI)",
                "Comparativa de entidades seleccionadas por identificador ROR / AF-ID en AGRI",
                "2025",
                "AGRI",
                0,
                "Custom",
                65.0,
                "workspace_seed (canonical ROR / AF-ID)",
                now_str,
            ),
        )
        run2_id = cur.lastrowid
        for ror_key, count in AGRI_COMPARISON_SEED:
            rec = seed_lookup[f"ror:{ror_key}"]
            q = _seed_default_query(rec, "2025", "AGRI")
            cur.execute(
                """
                INSERT INTO comparison_items
                (run_id, entity_uid, ror_id, afid, acronym, institution_name, category, inst_type, city, total_results, query_used)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    run2_id,
                    rec["entity_uid"],
                    rec["ror_id"],
                    rec["afid"],
                    rec["acronym"],
                    rec["name"],
                    rec["category"],
                    rec["inst_type"],
                    rec["city"],
                    count,
                    q,
                ),
            )

        # 3) All 63 Ecuadorian Universities
        cur.execute(
            """
            INSERT INTO comparison_runs
            (title, subtitle, year, subj_area, open_access_only, category_filter, reference_line, source, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "Publicaciones en todas las áreas — Universidades del Ecuador",
                "Evaluación nacional de 63 universidades e IES definidas por ROR / AF-ID",
                "2024",
                "ALL",
                0,
                "University",
                1142.0,
                "workspace_seed (canonical ROR / AF-ID)",
                now_str,
            ),
        )
        run3_id = cur.lastrowid
        for ror_id, afid, acr, cname, _lname, cat, itype, city, count, _variants, _dcity in ECUADOR_UNIVERSITIES_SEED:
            uid = compute_entity_uid(ror_id=ror_id, afid=afid, fallback_code=acr)
            rec = seed_lookup[f"uid:{uid}"]
            q = _seed_default_query(rec, "2024", "ALL")
            cur.execute(
                """
                INSERT INTO comparison_items
                (run_id, entity_uid, ror_id, afid, acronym, institution_name, category, inst_type, city, total_results, query_used)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (run3_id, rec["entity_uid"], rec["ror_id"], rec["afid"], acr, cname, cat, itype, city, count, q),
            )

    # Seed harvested publication datasets from existing CSVs in workspace if empty
    cur.execute("SELECT COUNT(*) FROM harvest_datasets")
    if cur.fetchone()[0] == 0:
        _seed_csv_datasets(conn)

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


def _seed_csv_datasets(conn: sqlite3.Connection) -> None:
    cur = conn.cursor()
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    inabio = find_institution(conn, "02veev176") or {
        "entity_uid": "ror:02veev176",
        "ror_id": "02veev176",
        "afid": "",
        "acronym": "INABIO",
        "name": "Instituto Nacional de Biodiversidad",
    }

    csv_2025 = WORKSPACE_DIR / "INABIO_Publications_2025_Standard.csv"
    if csv_2025.exists():
        with open(csv_2025, "r", encoding="utf-8", errors="replace") as f:
            reader = list(csv.DictReader(f))
        cur.execute(
            """
            INSERT INTO harvest_datasets
            (title, entity_uid, ror_id, afid, acronym, institution_name, year, view_mode, query_used, total_records, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "INABIO (ROR:02veev176) — Publicaciones 2025 (Standard View)",
                inabio["entity_uid"],
                inabio["ror_id"],
                inabio["afid"],
                inabio["acronym"],
                inabio["name"],
                "2025",
                "STANDARD",
                'AFFIL("Instituto Nacional de Biodiversidad") AND AFFILCOUNTRY(Ecuador) AND PUBYEAR = 2025',
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

    csv_2024 = WORKSPACE_DIR / "INABIO_Publications_2024_Final.csv"
    if csv_2024.exists():
        with open(csv_2024, "r", encoding="utf-8", errors="replace") as f:
            reader = list(csv.DictReader(f))
        cur.execute(
            """
            INSERT INTO harvest_datasets
            (title, entity_uid, ror_id, afid, acronym, institution_name, year, view_mode, query_used, total_records, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "INABIO (ROR:02veev176) — Publicaciones 2024 (Final Dataset)",
                inabio["entity_uid"],
                inabio["ror_id"],
                inabio["afid"],
                inabio["acronym"],
                inabio["name"],
                "2024",
                "STANDARD",
                'AFFIL("Instituto Nacional de Biodiversidad") AND AFFILCOUNTRY(Ecuador) AND PUBYEAR = 2024',
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
