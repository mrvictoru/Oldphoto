# Photo Restoration Demo (ComfyUI + FastAPI + FastHTML)

A minimal demo that sends a dynamically generated ComfyUI workflow to restore an uploaded photo and returns the processed image.

## How It Works
1. User uploads an image via a FastHTML frontend (served by FastAPI).
2. Backend loads a workflow template JSON (`Flux1 kontext photo restoration.json`), swaps the LoadImage node to point at the uploaded file URL, and POSTs it to ComfyUI (`/prompt`).
3. Backend listens on ComfyUI’s websocket, captures the `SaveImageWebsocket` node output, and streams the restored image back.

## Run with Docker Compose
1. Put required ComfyUI models / weights under `./comfyui` (adjust volumes in `docker-compose.yml` if needed) and have existing comfyui instance running (in a docker container).
2. Start:

    ```bash
    docker compose up --build
    ```
3. Open: http://localhost:8964

## Quick Local (No Docker) Smoke Test
1. Create venv and install FastAPI app deps:
    ```bash
    python -m venv .venv
    source .venv/bin/activate
    pip install -r fastapp/requirements.txt
    ```
2. Run API:
    ```bash
    uvicorn fastapp.main:app --host 0.0.0.0 --port 8000
    ```
3. Verify root HTML:
    ```bash
    curl -i http://127.0.0.1:8000/ | head -n 20
    # Expect /static/styles.css?v=... and /static/app.js?v=...
    ```

## Configuration
Environment variable:
- COMFYUI_HOST (e.g. `127.0.0.1:8288`) – where the backend reaches ComfyUI HTTP + websocket.

Static assets:
- Served from `fastapp/static` at `/static` with cache-busting query strings (mtime-based).

Workflow template:
- Based on a user-provided JSON. Node IDs / class names may differ across ComfyUI installs; adjust as needed.

## Notes / Caveats
- Remote image loading must be permitted by your ComfyUI instance for URL-based LoadImage usage. If not, mount the upload directory into the ComfyUI container and point the workflow to a local path.
- Security (auth, rate limiting, validation) is not included; add before production use.
- Adjust model paths inside the workflow if your file layout differs.

## Directory Sketch
- fastapp/ FastAPI + FastHTML code and static assets
- comfyui/ (mounted) models / weights (not included in repo)
- workflow template JSON (referenced by backend)

## Troubleshooting
- Image never returns: check websocket connectivity between backend and ComfyUI.
- 404 on static assets: ensure you are running from repo root so relative paths resolve.
- Cache not updating: modify time must change; touch the file or clear browser cache.

## Contributing
Open issues or PRs for workflow template adjustments or minimal reproducible bugs.

## Disclaimer
Demo or local use only; not hardened for production.
