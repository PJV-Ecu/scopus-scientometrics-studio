# Scopus Scientometrics & Aesthetic Graph Studio 📊

[![License: AGPL v3](https://img.shields.io/badge/License-AGPL_v3-blue.svg)](https://www.gnu.org/licenses/agpl-3.0)
[![Python: 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/)

An automated scientometrics web application for querying the **Elsevier Scopus API**, evaluating institutional research productivity (universities and research institutes), and generating publication-ready aesthetic data visualizations. Built with the assistance of Gemini Antigravity.

<img width="1886" height="1062" alt="2026-11-03 15 36 54" src="https://github.com/user-attachments/assets/2d879435-76c6-4ef4-85fe-b103fb7ccf4b" />

Built with a **zero-dependency Python 3.10+ standard library backend** and an interactive, responsive web frontend.

---

## ✨ Key Features

- **Automated Scopus Query Engine**:
  - Run multi-institution comparative queries with pagination, retry handling, and rate-limiting.
  - Harvest complete publication catalogs (titles, journals, publication dates, ISSN/ISBN, authors, co-affiliations, and DOIs).
  - Built-in institutional disambiguation using canonical **ROR** and **Scopus Affiliation IDs (AF-ID)** to eliminate international homonym skew (e.g., UNAE `01yg1g961`, UDLA `0198j4566` / `60104441`).

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
  - Pre-seeded with institutional profiles for 63 Ecuadorian universities and public research institutes (e.g., INABIO, INIAP, INSPI).

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
