# The AI Athlete – Railway Backend (FastAPI + MediaPipe)

This backend is **ready to deploy on Railway**. It lets your Android app (or a browser) upload a 10‑sec video, runs **pose tracking** (dots + lines overlay), **auto‑detects sport** (tennis/soccer/running with simple heuristics), generates **initial coaching tips**, and returns a **signed URL** to the overlay video.

**Endpoints**
- `GET /health` → `{ ok: true }`
- `GET /signed-upload?name=xxxx.mp4&contentType=video/mp4` → returns a signed **PUT** URL to upload directly to GCS (fast & reliable from phone)
- `POST /jobs { objectPath, sport? }` → starts analysis (sport optional; server will try to auto-detect if omitted)
- `GET /status/{jobId}` → returns `PENDING | PROCESSING | DONE | ERROR`, + `result` when ready
- `GET /test` → a tiny web page to try the flow without installing the app

## One‑time GCP setup
1) Create a **Google Cloud Storage bucket**, e.g. `ai-athlete-proto`.
2) Create a **service account** with role **Storage Object Admin** and download the **JSON key file**.
3) (Optional for web uploads) Set **CORS** on your bucket:
```json
[
  {
    "origin": ["*"],
    "method": ["PUT", "GET", "HEAD", "POST", "OPTIONS"],
    "responseHeader": ["Content-Type","Content-Length","x-goog-content-length-range"],
    "maxAgeSeconds": 3600
  }
]
```
Run: `gsutil cors set cors.json gs://YOUR_BUCKET`

## Deploy on Railway (no code needed)
1) Create a new GitHub repo; upload this folder’s files.
2) In Railway → **New Project → Deploy from GitHub** → select the repo.
3) In Railway → **Variables**, add:
   - `PORT` = `8080`
   - `GCS_BUCKET` = your bucket name (e.g., `ai-athlete-proto`)
   - `GOOGLE_APPLICATION_CREDENTIALS` = `/app/gcp.json`
   - `GCP_SERVICE_ACCOUNT_JSON_BASE64` = the **base64** of your service account JSON key
     - macOS: `base64 -i key.json | pbcopy`
     - Linux: `base64 key.json`
     - Windows (PowerShell): `[Convert]::ToBase64String([IO.File]::ReadAllBytes("key.json"))`
4) Click **Deploy**. When live, open `https://<your-railway-url>/health` → should return `{ "ok": true }`
5) Try the built‑in test page: `https://<your-railway-url>/test`

## How it works
- Your phone/app **requests a signed upload URL** → uploads the video **directly to GCS** (not to the API).
- Then the app calls **/jobs** with the objectPath → the server downloads the video, runs **MediaPipe Pose**, draws **dots/lines**, and uploads the **overlay** to `results/{jobId}.mp4`.
- The server **auto‑detects the sport** with simple motion heuristics and returns **starter recommendations**.
- The response includes a **signed URL** to stream the overlay video in the app.

## Next phases (built-in hooks)
- Replace the simple heuristic with your **real classifier** (ONNX/TensorRT/TF Lite).
- Add a **human coach workflow** that attaches feedback within 48 hours (e.g., via a coach portal or admin email → server writes coach notes back into job `result`).
- Switch to **Pub/Sub queue and GCP T4 worker** for heavy loads.
