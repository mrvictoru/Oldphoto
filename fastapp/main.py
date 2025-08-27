import os
import uuid
import json
import shutil
import time
import requests
from pathlib import Path
from fastapi import FastAPI, File, UploadFile, Form
from fastapi.responses import JSONResponse, FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles

import websocket

ROOT = Path(__file__).parent
UPLOAD_DIR = ROOT / 'uploads'
UPLOAD_DIR.mkdir(exist_ok=True)

app = FastAPI()
app.mount("/static", StaticFiles(directory=ROOT / 'static'), name="static")
app.mount("/uploads", StaticFiles(directory=UPLOAD_DIR), name="uploads")

COMFYUI_HOST = os.environ.get('COMFYUI_HOST', '127.0.0.1:8188')


def send_prompt_to_comfy(prompt_json, client_id: str):
    url = f"http://{COMFYUI_HOST}/prompt"
    payload = {"prompt": prompt_json, "client_id": client_id}
    resp = requests.post(url, json=payload, timeout=30)
    resp.raise_for_status()
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
            # binary frame
            if current_node == 'save_image_websocket_node':
                images_output = output_images.get(current_node, [])
                # strip websocket binary header if present (example sample used out[8:])
                try:
                    data_bytes = out[8:]
                except Exception:
                    data_bytes = out
                images_output.append(data_bytes)
                output_images[current_node] = images_output

    ws.close()
    return output_images


@app.get('/')
def index():
    html_path = ROOT / 'static' / 'index.html'
    return HTMLResponse(html_path.read_text())


@app.post('/restore')
def restore(file: UploadFile = File(...)):
    # Save uploaded file
    uid = uuid.uuid4().hex
    filename = f"upload_{uid}_{file.filename}"
    file_path = UPLOAD_DIR / filename
    with file_path.open('wb') as f:
        shutil.copyfileobj(file.file, f)

    # Load workflow template and set uploaded filename
    template_path = ROOT / 'workflow_template.json'
    workflow = json.loads(template_path.read_text())
    # Replace placeholder for LoadImage node
    # The template uses "__UPLOAD_FILENAME__" as placeholder
    # Set to path relative to the ComfyUI server; we also provide a simple endpoint to fetch the uploaded file
    # ComfyUI can accept remote URLs for LoadImage if configured; here we'll point to our app's uploads endpoint.
    upload_url = f"http://{os.environ.get('APP_HOST', '127.0.0.1:8964')}/uploads/{filename}"
    # set node 203 image field if exists
    if '203' in workflow and 'inputs' in workflow['203']:
        workflow['203']['inputs']['image'] = upload_url
    else:
        # try to find a LoadImage node
        for k, v in workflow.items():
            if isinstance(v, dict) and v.get('class_type') == 'LoadImage':
                v.setdefault('inputs', {})['image'] = upload_url

    # ensure there is a SaveImageWebsocket node pointing to the main VAEDecode output (111)
    workflow['save_image_websocket_node'] = {
        "class_type": "SaveImageWebsocket",
        "inputs": {"images": ["111", 0]}
    }

    # send prompt
    client_id = str(uuid.uuid4())
    resp = send_prompt_to_comfy(workflow, client_id)
    prompt_id = resp.get('prompt_id')

    images = get_images_via_ws(prompt_id, client_id, timeout=90)

    after_urls = []
    saved_after_files = []
    node_images = images.get('save_image_websocket_node', [])
    for i, img_bytes in enumerate(node_images):
        out_name = f"restored_{uid}_{i}.png"
        out_path = UPLOAD_DIR / out_name
        with out_path.open('wb') as f:
            f.write(img_bytes)
        saved_after_files.append(out_path)
        after_urls.append(f"/uploads/{out_name}")

    # return first restored image and original upload for comparison
    result = {
        'before': f"/uploads/{filename}",
        'after': after_urls[0] if after_urls else None,
        'all_after': after_urls
    }
    return JSONResponse(result)
