# Universal AI Dashboard Generator

Upload almost any CSV and get a cleaned dataset, ten evidence-based insights, an adaptive Streamlit dashboard, a PDF report, and a scheduled daily email.

> The app's automated findings are generated from the actual dataset. An optional OpenAI summary turns those findings into a short executive narrative; it never replaces the measured results.

## What it does

- Reads CSV files with encoding and delimiter fallback.
- Cleans column names, whitespace, blank values, duplicate rows, numeric values, and likely date fields.
- Produces ten transparent insights: data quality, distributions, correlations, trends, category concentration, outliers, and more.
- Builds exploratory Plotly charts from the available fields.
- Creates a shareable PDF report and can email it immediately.
- Runs as a durable scheduler process that emails the latest processed dataset at 7:00 AM in your configured timezone.

## Quick start

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env
streamlit run app.py
```

Open the local URL Streamlit prints, upload a CSV, then use the **Automation** panel to save the cleaned dataset, generate the report, test email delivery, or start the scheduler.

For a fast tour, upload `data/sample_sales.csv`.

## Daily report scheduler

The Streamlit process is designed for exploration. Run the scheduler separately so it remains active after the browser is closed:

```bash
python -m src.scheduler
```

It uses `data/latest_cleaned.csv`, which the app saves whenever you click **Save for daily automation**. Configure SMTP and the delivery time in `.env`. To test the entire scheduled flow now:

```bash
python -m src.scheduler --run-now
```

For production, keep that command alive with your platform's process manager, Windows Task Scheduler, Docker, or a small VM. It must be running at 7:00 AM to send the email.

## Docker (dashboard + scheduler)

After copying `.env.example` to `.env`, start both persistent services with:

```bash
docker compose up --build
```

Visit `http://localhost:8501`, upload your CSV, and save it for automation. The dashboard and scheduler share persistent Docker volumes for the cleaned dataset and generated reports.

## Optional AI narrative

Set `OPENAI_API_KEY` in `.env` to add a compact executive summary generated from the already-computed findings. Without it, the dashboard and PDF still work fully using deterministic analytics.

## Privacy note

CSV files are processed locally. If you enable the OpenAI narrative, only schema-level statistics and the generated findings are sent for summarization; raw rows are not sent.

## Project structure

```text
app.py                  # Streamlit UI
src/cleaning.py         # robust CSV parsing and cleaning
src/insights.py         # deterministic, traceable insight engine
src/llm.py              # optional executive-summary enrichment
src/reporting.py        # PDF creation
src/emailer.py          # SMTP delivery
src/scheduler.py        # daily 7am job
```
