---
title: Scopus Scientometrics Studio
emoji: 📊
colorFrom: green
colorTo: indigo
sdk: docker
app_port: 7860
pinned: false
---

# Scopus Scientometrics & Aesthetic Graph Studio

Web application for automated queries to the Elsevier Scopus API, scientometric productivity assessment of universities and public research institutes, and production of publication-ready aesthetic figures (Lollipop charts, horizontal/vertical bar plots, circular radial charts, and word clouds).

## Configuration (Hugging Face Secrets)
In your Space **Settings** -> **Variables and secrets**, define:
- `SCOPUS_API_KEY`: Your 32-character Scopus API key from Elsevier Developer Portal.
- `APP_PASSWORD`: Secure password to restrict access to the application.
- (Optional) `APP_USERNAME`: Username for authentication (defaults to `admin`).

