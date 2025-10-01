import os, uuid, time, tempfile
from typing import Dict, Any
from fastapi import FastAPI, HTTPException, Query, Body
from fastapi.responses import HTMLResponse
from google.cloud import storage
from .pose_overlay import process_video_and_overlay
from .signed_urls import get_v4_signed_put_url, get_v4_signed_get_url

app = FastAPI(title="AI Athlete Backend")
BUCKET = os.environ.get("GCS_BUCKET")
if not BUCKET:
    raise RuntimeError("GCS_BUCKET is required")

storage_client = storage.Client()
JOBS: Dict[str, Dict[str, Any]] = {}

@app.get("/health")
def health():
    return {"ok": True}

@app.get("/test")
def test_page():
    return HTMLResponse("""<!doctype html>
<html><head><meta charset='utf-8'><title>AI Athlete Test</title>
<style>body{font-family:system-ui;margin:24px}button{padding:10px 16px}</style></head>
<body>
<h2>Upload & Analyze (Prototype)</h2>
<label>Sport (optional): 
<select id="sport">
  <option value="">Auto</option>
  <option>tennis</option>
  <option>soccer</option>
  <option>running</option>
</select>
</label><br/><br/>
<input id='file' type='file' accept='video/mp4,video/*'/>
<button id='go'>Upload & Analyze</button>
<pre id='out'></pre>
<script>
const api = location.origin;
const out = document.getElementById('out');
document.getElementById('go').onclick = async () => {
  try {
    const f = document.getElementById('file').files[0];
    if(!f){ out.textContent='Pick a short video (<=10s)'; return; }
    const name = Date.now() + '.mp4';
    out.textContent='Requesting signed URL...\n';
    const s = await fetch(api + '/signed-upload?name='+encodeURIComponent(name)+'&contentType='+encodeURIComponent(f.type||'video/mp4'));
    const {url, objectPath} = await s.json();
    out.textContent+='Uploading...\n';
    const put = await fetch(url, { method:'PUT', headers:{'Content-Type': f.type||'video/mp4'}, body: f });
    if(!put.ok) throw new Error('Upload failed '+put.status);
    const sport = document.getElementById('sport').value || null;
    out.textContent+='Creating job...\n';
    const j = await fetch(api + '/jobs', {method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({objectPath, sport})});
    const {id} = await j.json();
    out.textContent+='Processing...\n';
    const poll = async () => {
      const r = await fetch(api + '/status/'+id);
      const data = await r.json();
      if(data.status==='DONE' || data.status==='ERROR'){
        out.textContent += '\n' + JSON.stringify(data, null, 2);
      } else {
        setTimeout(poll, 1200);
      }
    };
    poll();
  } catch(e){ out.textContent += '\nError: '+e.message; }
};
</script>
</body></html>""")

@app.get("/signed-upload")
def signed_upload(name: str = Query(...), contentType: str = Query("video/mp4")):
    url = get_v4_signed_put_url(storage_client, BUCKET, f"uploads/{name}", contentType)
    return {"url": url, "objectPath": f"uploads/{name}", "contentType": contentType}

@app.post("/jobs")
def create_job(payload: Dict[str, Any] = Body(...)):
    object_path = payload.get("objectPath")
    sport = payload.get("sport")
    if not object_path:
        raise HTTPException(status_code=400, detail="objectPath required")
    job_id = str(uuid.uuid4())
    JOBS[job_id] = {"status": "PENDING", "result": None, "ts": time.time()}
    try:
        JOBS[job_id]["status"] = "PROCESSING"
        bucket = storage_client.bucket(BUCKET)
        blob = bucket.blob(object_path)
        with tempfile.TemporaryDirectory() as d:
            input_path = os.path.join(d, "input.mp4")
            blob.download_to_filename(input_path)
            output_blob_path = f"results/{job_id}.mp4"
            overlay_info = process_video_and_overlay(
                input_path=input_path,
                output_blob_path=output_blob_path,
                bucket=bucket,
                provided_sport=sport
            )
            overlay_url = get_v4_signed_get_url(storage_client, BUCKET, output_blob_path, minutes=60*24)
            JOBS[job_id]["status"] = "DONE"
            JOBS[job_id]["result"] = {
                "sport": overlay_info["sport"],
                "metrics": overlay_info["metrics"],
                "summary": overlay_info["summary"],
                "drills": overlay_info["drills"],
                "overlay_url": overlay_url
            }
    except Exception as e:
        JOBS[job_id]["status"] = "ERROR"
        JOBS[job_id]["result"] = {"message": str(e)}
    return {"id": job_id, "status": JOBS[job_id]["status"]}

@app.get("/status/{job_id}")
def status(job_id: str):
    j = JOBS.get(job_id)
    if not j:
        raise HTTPException(status_code=404, detail="Not found")
    return {"id": job_id, "status": j["status"], "result": j["result"]}


COACH_WEBHOOK_TOKEN = os.environ.get("COACH_WEBHOOK_TOKEN", "")

from fastapi import Header

@app.post("/coach-feedback")
def coach_feedback(payload: Dict[str, Any] = Body(...), x_token: str = Header(default="")):
    if not COACH_WEBHOOK_TOKEN or x_token != COACH_WEBHOOK_TOKEN:
        raise HTTPException(status_code=401, detail="Unauthorized")
    job_id = payload.get("jobId")
    notes = payload.get("coachNotes")
    if not job_id or not isinstance(notes, str):
        raise HTTPException(status_code=400, detail="jobId and coachNotes required")
    j = JOBS.get(job_id)
    if not j:
        raise HTTPException(status_code=404, detail="job not found")
    if j.get("result") is None:
        j["result"] = {}
    j["result"]["coach_feedback"] = notes
    return {"ok": True}
