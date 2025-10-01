# app/main.py
import os, uuid
from typing import Dict, Any
from fastapi import FastAPI, Body, HTTPException, Query
from fastapi.responses import HTMLResponse
from google.cloud import storage
import cv2
import numpy as np
import mediapipe as mp

app = FastAPI()
BUCKET = os.environ.get("GCS_BUCKET", "")
if not BUCKET:
    raise RuntimeError("GCS_BUCKET env var not set")

JOBS: Dict[str, Dict[str, Any]] = {}

storage_client = storage.Client()
bucket = storage_client.bucket(BUCKET)

def gcs_signed_put(object_name: str, content_type: str = "video/mp4", minutes: int = 15):
    blob = bucket.blob(object_name)
    url = blob.generate_signed_url(
        version="v4", expiration=60*minutes, method="PUT", content_type=content_type
    )
    return {"url": url, "objectPath": object_name}

def gcs_signed_get(object_name: str, minutes: int = 60):
    return bucket.blob(object_name).generate_signed_url(
        version="v4", expiration=60*minutes, method="GET"
    )

@app.get("/health")
def health(): return {"ok": True}

@app.get("/signed-upload")
def signed_upload(name: str = Query(...), contentType: str = Query("video/mp4")):
    object_path = f"uploads/{name}"
    return {"url": gcs_signed_put(object_path, contentType)["url"], "objectPath": object_path}

@app.post("/jobs")
def create_job(payload: Dict[str, Any] = Body(...)):
    object_path = payload.get("objectPath")
    if not object_path:
        raise HTTPException(400, "objectPath required")
    job_id = str(uuid.uuid4())
    JOBS[job_id] = {"status": "PROCESSING", "object_path": object_path, "result": None}

    try:
        tmp_in = f"/tmp/{job_id}.mp4"
        bucket.blob(object_path).download_to_filename(tmp_in)

        mp_pose = mp.solutions.pose
        pose = mp_pose.Pose(static_image_mode=False)
        cap = cv2.VideoCapture(tmp_in)
        w  = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        h  = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        fps= cap.get(cv2.CAP_PROP_FPS) or 24
        fourcc = cv2.VideoWriter_fourcc(*"mp4v")
        tmp_out = f"/tmp/{job_id}_overlay.mp4"
        out = cv2.VideoWriter(tmp_out, fourcc, fps, (w, h))

        while True:
            ok, frame = cap.read()
            if not ok: break
            rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            res = pose.process(rgb)
            if res.pose_landmarks:
                for lm in res.pose_landmarks.landmark:
                    cx, cy = int(lm.x * w), int(lm.y * h)
                    cv2.circle(frame, (cx, cy), 3, (0,255,0), -1)
            out.write(frame)

        cap.release(); out.release(); pose.close()

        result_gcs = f"results/{job_id}.mp4"
        bucket.blob(result_gcs).upload_from_filename(tmp_out, content_type="video/mp4")

        sport = payload.get("sport") or "tennis/soccer/running (auto-demo)"

        JOBS[job_id]["status"] = "DONE"
        JOBS[job_id]["result"] = {
            "sport": sport,
            "summary": "Starter tips based on posture/tempo.",
            "metrics": {},
            "drills": ["Shadow swings x20", "Footwork ladder 2x", "Hip mobility 5min"],
            "overlay_url": gcs_signed_get(result_gcs),
        }
    except Exception as e:
        JOBS[job_id]["status"] = "ERROR"
        JOBS[job_id]["result"] = {"error": str(e)}
    return {"id": job_id}

@app.get("/status/{job_id}")
def status(job_id: str):
    j = JOBS.get(job_id)
    if not j: raise HTTPException(404, "not found")
    return {"status": j["status"], "result": j["result"]}

@app.get("/test", response_class=HTMLResponse)
def test():
    return """<!doctype html><html><body style="font-family:sans-serif">
<h2>AI Athlete – Quick Test</h2>
<input type="file" id="file"><button onclick="go()">Upload & Analyze</button>
<pre id="log"></pre><video id="v" controls style="max-width:480px"></video>
<script>
const base = location.origin;
async function go(){
  const f = document.getElementById('file').files[0];
  if(!f){ alert('pick a file'); return; }
  const r1 = await fetch(`${base}/signed-upload?name=${Date.now()}.mp4&contentType=${f.type||'video/mp4'}`);
  const {url, objectPath} = await r1.json();
  await fetch(url, {method:'PUT', body:f, headers:{'Content-Type': f.type||'video/mp4'}});
  const r2 = await fetch(`${base}/jobs`, {method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({objectPath})});
  const {id} = await r2.json();
  let s={status:'PROCESSING'};
  while(s.status==='PROCESSING'){ await new Promise(t=>setTimeout(t,1500)); s = await (await fetch(`${base}/status/`+id)).json(); }
  document.getElementById('log').textContent = JSON.stringify(s,null,2);
  if(s.result && s.result.overlay_url){ document.getElementById('v').src = s.result.overlay_url; }
}
</script></body></html>"""
