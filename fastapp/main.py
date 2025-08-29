import os
import uuid
import json
import shutil
import time
import threading
import requests
from pathlib import Path
from urllib.parse import quote
import re
from typing import List
from fastapi import FastAPI, File, UploadFile, HTTPException
from starlette.status import HTTP_400_BAD_REQUEST
try:
    from PIL import Image
except ImportError:
    Image = None
def is_image_file(file: UploadFile, file_path: Path):
    # Prefer to validate by attempting to open the file with Pillow (best-opinion)
    if Image is not None:
        try:
            with Image.open(file_path) as img:
                img.verify()
        except Exception:
            return False, "Uploaded file is not a valid image."
        return True, ""

    # Fallback checks if Pillow not available: MIME and extension
    if not file.content_type or not file.content_type.startswith('image/'):
        return False, "Uploaded file is not an image (invalid MIME type)."
    allowed_ext = {'.jpg', '.jpeg', '.png', '.webp'}
    ext = file.filename.lower().rsplit('.', 1)[-1] if '.' in file.filename else ''
    if f'.{ext}' not in allowed_ext:
        return False, f"File extension .{ext} is not allowed. Allowed: {', '.join(allowed_ext)}."
    return True, ""
from fastapi.responses import JSONResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles

import websocket

ROOT = Path(__file__).parent
UPLOAD_DIR = ROOT / 'uploads'
UPLOAD_DIR.mkdir(exist_ok=True)

# Simple job history persistence (basic JSON file). Not for heavy production use.
HISTORY_FILE = UPLOAD_DIR / 'history.json'
_history_lock = threading.Lock()
if HISTORY_FILE.exists():
    try:
        HISTORY = json.loads(HISTORY_FILE.read_text())
        if not isinstance(HISTORY, list):
            HISTORY = []
    except Exception:
        HISTORY = []
else:
    HISTORY = []

def _save_history():
    with _history_lock:
        try:
            HISTORY_FILE.write_text(json.dumps(HISTORY, indent=2))
        except Exception:
            pass

app = FastAPI()
app.mount("/static", StaticFiles(directory=ROOT / 'static'), name="static")
app.mount("/uploads", StaticFiles(directory=UPLOAD_DIR), name="uploads")

COMFYUI_HOST = os.environ.get('COMFYUI_HOST', '127.0.0.1:8288')
COMFY_TIMEOUT = int(os.environ.get('COMFY_TIMEOUT', '900'))  # seconds max wait


def send_prompt_to_comfy(prompt_json, client_id: str):
    url = f"http://{COMFYUI_HOST}/prompt"
    payload = {"prompt": prompt_json, "client_id": client_id}
    print(f"[DEBUG] Sending to ComfyUI: {url} payload={{'prompt': ...}} client_id={client_id}")
    try:
        resp = requests.post(url, json=payload, timeout=30)
        print(f"[DEBUG] ComfyUI response: {resp.status_code} {resp.text[:500]}")
    except Exception as e:
        print(f"[ERROR] Exception during POST to ComfyUI: {e}")
        raise
    if not resp.ok:
        detail = f"Upstream ComfyUI error {resp.status_code}: {resp.text[:400]}"
        raise HTTPException(status_code=500, detail=detail)
    return resp.json()


def get_images_via_ws(prompt_id, client_id, timeout=60):
    ws_url = f"ws://{COMFYUI_HOST}/ws?clientId={client_id}"
    ws = websocket.WebSocket()
    ws.connect(ws_url)

    output_images = {}
    current_node = ""
    start = time.time()
    while True:
        if time.time() - start > timeout:
            print(f"[DEBUG] Websocket timeout reached ({timeout}s) for prompt {prompt_id}")
            break
        out = ws.recv()
        if isinstance(out, str):
            message = json.loads(out)
            if message.get('type') == 'executing':
                data = message.get('data', {})
                if data.get('prompt_id') == prompt_id:
                    if data.get('node') is None:
                        break
                    else:
                        current_node = data.get('node')
        else:
            # binary frame -> associate with most recently executing node (likely a SaveImage / Preview node)
            images_output = output_images.get(current_node, [])
            try:
                data_bytes = out[8:]  # strip potential header
            except Exception:
                data_bytes = out
            images_output.append(data_bytes)
            output_images[current_node] = images_output

    ws.close()
    return output_images


def fetch_history_images(prompt_id: str) -> List[bytes]:
    """Fallback: query ComfyUI history for outputs and download images via /view endpoint."""
    hist_url = f"http://{COMFYUI_HOST}/history/{prompt_id}"
    try:
        r = requests.get(hist_url, timeout=30)
        if not r.ok:
            print(f"[DEBUG] History fetch failed {r.status_code}: {r.text[:200]}")
            return []
        data = r.json()
    except Exception as e:
        print(f"[DEBUG] Exception fetching history: {e}")
        return []
    # ComfyUI history structure: { prompt_id: { 'outputs': { node_id: { 'images': [ {filename, subfolder, type}, ... ] } } } }
    prompt_blob = data.get(prompt_id) or {}
    outputs = prompt_blob.get('outputs', {})
    collected: List[bytes] = []
    for node_id, node_out in outputs.items():
        for img_meta in node_out.get('images', []):
            fname = img_meta.get('filename')
            subfolder = img_meta.get('subfolder', '')
            img_type = img_meta.get('type', 'output')  # usually 'output'
            if not fname:
                continue
            params = {
                'filename': fname,
                'subfolder': subfolder,
                'type': img_type
            }
            try:
                view_url = f"http://{COMFYUI_HOST}/view"
                ir = requests.get(view_url, params=params, timeout=60)
                if ir.ok:
                    collected.append(ir.content)
                else:
                    print(f"[DEBUG] Failed to fetch image {fname}: {ir.status_code}")
            except Exception as e:
                print(f"[DEBUG] Exception fetching image {fname}: {e}")
    return collected


@app.get('/')
def index():
    html_path = ROOT / 'static' / 'index.html'
    return HTMLResponse(html_path.read_text())


@app.post('/restore')
def restore(file: UploadFile = File(...)):

    # Save uploaded file (sanitize filename)
    uid = uuid.uuid4().hex
    raw_name = Path(file.filename).name
    safe_name = re.sub(r'[^A-Za-z0-9._-]', '_', raw_name)
    filename = f"upload_{uid}_{safe_name}"
    file_path = UPLOAD_DIR / filename
    with file_path.open('wb') as f:
        shutil.copyfileobj(file.file, f)

    # File verification
    ok, err = is_image_file(file, file_path)
    if not ok:
        file_path.unlink(missing_ok=True)
        raise HTTPException(status_code=HTTP_400_BAD_REQUEST, detail=err)

    # Load workflow template and set uploaded filename
    template_path = ROOT / 'workflow_template.json'
    workflow = json.loads(template_path.read_text())
    print(f"[DEBUG] Loading workflow from: {template_path}")
    # Replace placeholder "__UPLOAD_FILENAME__" with path readable by ComfyUI
    # The shared volume should be mounted into ComfyUI at /root/ComfyUI/input
    # Use the absolute in-container path so ComfyUI can open the file directly.
    comfy_path = f"/root/ComfyUI/input/{filename}"
    # set node 203 image field if exists
    if '203' in workflow and 'inputs' in workflow['203']:
        workflow['203']['inputs']['image'] = comfy_path
    else:
        # try to find a LoadImage node
        for k, v in workflow.items():
            if isinstance(v, dict) and v.get('class_type') == 'LoadImage':
                v.setdefault('inputs', {})['image'] = comfy_path

    # Note: We no longer inject a synthetic websocket save node; relying on existing SaveImage nodes in the workflow.

    # send prompt
    client_id = str(uuid.uuid4())
    resp = send_prompt_to_comfy(workflow, client_id)
    prompt_id = resp.get('prompt_id')

    # Attempt to capture images via websocket first (long timeout)
    images = get_images_via_ws(prompt_id, client_id, timeout=COMFY_TIMEOUT)

    after_urls = []
    saved_after_files = []
    # Collect images from any node that produced binary frames (prefer SaveImage nodes if present)
    candidate_nodes = [k for k in images.keys()]
    node_images = []
    # heuristic: choose node with most images
    if candidate_nodes:
        primary_node = max(candidate_nodes, key=lambda k: len(images.get(k, [])))
        node_images = images.get(primary_node, [])

    # Fallback: if no websocket images, try history API
    if not node_images:
        print("[DEBUG] No websocket images received; attempting history fetch")
        node_images = fetch_history_images(prompt_id)
    for i, img_bytes in enumerate(node_images):
        out_name = f"restored_{uid}_{i}.png"
        out_path = UPLOAD_DIR / out_name
        with out_path.open('wb') as f:
            f.write(img_bytes)
        saved_after_files.append(out_path)
        after_urls.append(f"/uploads/{out_name}")

    # return first restored image and original upload for comparison
    job = {
        'job_id': uid,
        'created': int(time.time()),
        'before': f"/uploads/{filename}",
        'after': after_urls[0] if after_urls else None,
        'all_after': after_urls
    }
    with _history_lock:
        HISTORY.append(job)
    _save_history()
    return JSONResponse(job)


@app.get('/history')
def history_list():
    # Return most recent first
    with _history_lock:
        return JSONResponse(list(reversed(HISTORY[-200:])))


@app.get('/history/{job_id}')
def history_item(job_id: str):
    with _history_lock:
        for j in HISTORY:
            if j.get('job_id') == job_id:
                return JSONResponse(j)
    return JSONResponse({'error': 'not_found'}, status_code=404)
