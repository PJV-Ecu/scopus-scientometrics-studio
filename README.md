# Scopus Scientometrics & Aesthetic Graph Studio 📊

[![License: AGPL v3](https://img.shields.io/badge/License-AGPL_v3-blue.svg)](https://www.gnu.org/licenses/agpl-3.0)
[![Python: 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/)

An automated scientometrics web application for querying the **Elsevier Scopus API**, evaluating institutional research productivity (universities and research institutes), and generating publication-ready aesthetic data visualizations. Built with the assistance of Gemini Antigravity.

<img width="1886" height="1062" alt="2026-11-03 15 36 54" src="https://github.com/user-attachments/assets/2d879435-76c6-4ef4-85fe-b103fb7ccf4b" />

Built with a **zero-dependency Python 3.10+ standard library backend** and an interactive, responsive web frontend.

---

## ✨ Key Features

- **Identifier-First Entity Resolution (`Scopus AF-ID` & `ROR`)**:
  - Entities (universities and research institutes) are defined and referenced canonically by their **Scopus Affiliation Identifier (`AF-ID`)** and **Research Organization Registry (`ROR`)** ID rather than fragile institution name strings.
  - Pure `AF-ID(...)` Scopus queries whenever an entity has a curated Scopus institutional profile (`60xxxxxx`), with automatic live `AF-ID` discovery & caching via Elsevier's API and ROR-backed disambiguated fallback for unprofiled entities.
  - Harvest complete publication catalogs (titles, journals, publication dates, ISSN/ISBN, authors, co-affiliations, and DOIs), isolating institutional authors directly by `AF-ID`.

- **Publication-Ready Aesthetic Graphs**:
  - **Graph Types**: Horizontal Lollipop (`geom_segment` + `geom_point`), Ranked Bars, Vertical Columns, Circular Radial Charts, and City/Sector aggregations.
  - **Curated Themes**: *Pomological Painted* (watercolor parchment & `Bears` palette), *Solarized Light & Dark*, *Nature/Editorial*, and *Viridis*.
  - **Customizable Layouts**: Live adjustment of titles, labels, reference thresholds (`xintercept`), sector filters (Public vs. Private), and top-$N$ rankings.

- **Word Clouds & Text Analytics**:
  - Generate collision-free spiral word clouds and frequency bar charts from **Article Titles**, **Journals**, **Collaborating Institutions**, or **Authors**.
  - Built-in bilingual (English/Spanish) stopword filtering and customizable exclusion lists.

- **High-Resolution Vector & Data Export**:
  - Download publication-grade figures in **Vector SVG** and **300-DPI PNG**.
  - Export ranked comparisons and publication catalogs to **Excel (`.xlsx`)** and **CSV**.

- **Zero-Dependency Architecture**:
  - Runs natively on Python 3.10+ without requiring external package installations (`pip`).
  - Pre-seeded with canonical `AF-ID` / `ROR` profiles for **63 Ecuadorian universities** and **7 public research institutes** (INABIO, INIAP, INSPI, IIGE, IPIAP, IG-EPN, INOCAR).

---

## 🚀 Quick Start

### 1. Clone the repository
```bash
git clone https://github.com/PJV-Ecu/scopus-scientometrics-studio.git
cd scopus-scientometrics-studio
```

### 2. Run the application
```bash
./run_app.sh
```
*(Or directly with Python: `python3 scopus_app/app.py`)*

### 3. Open in your browser
Navigate to **`http://localhost:8080`**.

---

## 🔒 Configuration & Environment Variables

The application can read credentials from the web UI (`Settings` tab) or via environment variables:

| Variable | Description |
| :--- | :--- |
| `SCOPUS_API_KEY` | *(Optional)* Your 32-character Scopus API key from the Elsevier Developer Portal. |
| `APP_PASSWORD` | *(Optional)* Set a password to restrict web access when hosting publicly. |
| `APP_USERNAME` | *(Optional)* Username for authentication (defaults to `admin`). |
| `PORT` | *(Optional)* HTTP server port (defaults to `8080`, or `10000`/`7860` in cloud environments). |

---

## 📄 License
This project is open-source and licensed under the [GNU Affero General Public License v3.0 (GNU AGPLv3)](LICENSE).
