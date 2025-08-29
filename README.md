Photo restoration demo using ComfyUI + FastAPI + FastHTML frontend.

How it works
- The FastAPI app serves a simple FastHTML-based frontend where users upload an image.
- The backend constructs a ComfyUI workflow JSON (based on the provided `Flux1 kontext photo restoration.json` template), replaces the LoadImage node with a URL pointing to the uploaded file, and posts it to ComfyUI's HTTP `/prompt` endpoint.
- The backend connects to ComfyUI's websocket to capture a SaveImageWebsocket node output and returns the restored image to the frontend.

Run locally with Docker Compose
1. Place your ComfyUI models and weights in `./comfyui` or adjust the compose volumes.
2. Build and start:

    docker compose up --build

3. Open http://localhost:8000

Notes and caveats
- This example expects ComfyUI to accept remote image URLs in the LoadImage node. If your ComfyUI is not configured to fetch remote images, you can mount the uploads directory into the ComfyUI container and point the workflow to the mounted path instead.
- The provided workflow template is derived from the user's JSON. Depending on your ComfyUI installation, node IDs or classes may differ; you may need to adjust the JSON template.
- For production, secure the endpoints and add authentication and input validation.

Quick smoke test (without Docker)

1. Create a Python venv and install requirements for the FastAPI app:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r fastapp/requirements.txt
```

2. Run the FastAPI app locally (binds to 127.0.0.1:8000 by default when using uvicorn):

```bash
uvicorn fastapp.main:app --host 0.0.0.0 --port 8000
```

3. In another terminal, verify the root responds and the HTML contains the cache-busted assets:

```bash
curl -i http://127.0.0.1:8000/ | head -n 20
# Look for "/static/styles.css?v=" and "/static/app.js?v=" in the HTML
```

Notes
- The app serves static files from `fastapp/static` at the `/static` URL path. The cache-busting query string is derived from file modification times so browsers will reload assets after changes.
- To run end-to-end, you still need a running ComfyUI instance reachable by setting the `COMFYUI_HOST` environment variable (e.g. `127.0.0.1:8288`).
