# Deployment

The image is self-sufficient: `docker/entrypoint.sh` builds the warehouse on
first boot if it's missing (discovering the latest quarters automatically), then
starts the requested service. Scope is controlled by `PULSE_MIN_YEAR` /
`PULSE_MAX_YEAR`; the DB path by `PULSE_DB_PATH`.

## Option A — Docker Compose (local / any VM)

```bash
docker compose up --build
# API   -> http://localhost:8000/docs
# Dash  -> http://localhost:8501
```

A one-shot `pipeline` service populates a shared `pulse-data` volume; the API and
dashboard start once it succeeds and reuse the volume.

## Option B — Render (managed, from `render.yaml`)

Push to GitHub, then Render → **New → Blueprint** and select the repo. It creates
two Docker web services (`upi-api`, `upi-dashboard`) from the one `Dockerfile`,
each self-building its warehouse on first boot. Adjust `PULSE_MIN_YEAR/MAX_YEAR`
env vars to trade coverage for cold-start time.

> Free-tier web services sleep when idle and rebuild the warehouse on wake. For an
> always-warm demo, use a paid instance or attach a persistent disk at
> `/app/data` so the warehouse survives restarts.

## Option C — Streamlit Community Cloud (dashboard only, free)

1. Push the repo to GitHub.
2. share.streamlit.io → **New app** → main file `dashboard/app.py`.
3. In **Advanced settings → Secrets/Env**, set `PULSE_AUTO_BUILD = "1"` (and
   optionally `PULSE_MIN_YEAR` / `PULSE_MAX_YEAR`).

On first load the app builds the warehouse from the public Pulse dataset (cached
for the session). `requirements.txt` is installed automatically.

**File discovery on shared hosts.** Discovery normally uses the GitHub trees API,
which is rate-limited to 60 requests/hour per IP — and cloud hosts share IPs, so
it can 403. The pipeline handles this automatically by falling back to a bundled
manifest (`src/ingestion/pulse_manifest.json`), so builds work without the API.
To instead use the live API (and auto-discover brand-new quarters), add a
`GITHUB_TOKEN` secret with a read-only token (raises the limit to 5000/hour).

## Option D — Fly.io / Cloud Run

Any single-container host works with the same image:

```bash
# Fly
fly launch --dockerfile Dockerfile
fly deploy
# Cloud Run
gcloud run deploy upi-dashboard --source . \
  --command streamlit --args "run,dashboard/app.py,--server.port,8080,--server.address,0.0.0.0"
```

Set the same `PULSE_*` env vars. Mount/attach a volume at `/app/data` if you want
the warehouse to persist across restarts.

## Keeping data fresh

`.github/workflows/refresh-data.yml` re-ingests weekly (and on demand), runs the
data-quality checks (failing the job on any FAIL), and uploads the rebuilt
warehouse as an artifact a deployment can pull. New quarters are picked up
automatically by the discovery step — no code change needed.
