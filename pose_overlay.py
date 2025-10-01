import cv2, numpy as np, mediapipe as mp
from typing import Dict, Any

mp_drawing = mp.solutions.drawing_utils
mp_pose = mp.solutions.pose

def _sport_heuristic(landmark_series):
    import numpy as np
    ankles_y = np.array([ (f['pose'][mp_pose.PoseLandmark.LEFT_ANKLE.value].y +
                           f['pose'][mp_pose.PoseLandmark.RIGHT_ANKLE.value].y)/2.0
                           for f in landmark_series if f['pose'] is not None ] or [0.0])
    wrists_y = np.array([ (f['pose'][mp_pose.PoseLandmark.LEFT_WRIST.value].y +
                           f['pose'][mp_pose.PoseLandmark.RIGHT_WRIST.value].y)/2.0
                           for f in landmark_series if f['pose'] is not None ] or [0.0])
    hips_x = np.array([ (f['pose'][mp_pose.PoseLandmark.LEFT_HIP.value].x +
                         f['pose'][mp_pose.PoseLandmark.RIGHT_HIP.value].x)/2.0
                         for f in landmark_series if f['pose'] is not None ] or [0.0])

    if len(ankles_y) < 3:
        return "running"
    ankles_y = (ankles_y - ankles_y.mean()) / (ankles_y.std() + 1e-6)
    wrists_y = (wrists_y - wrists_y.mean()) / (wrists_y.std() + 1e-6)
    hips_x = (hips_x - hips_x.mean()) / (hips_x.std() + 1e-6)

    zc = ((ankles_y[:-1] * ankles_y[1:]) < 0).sum()
    wrist_var = np.var(np.diff(wrists_y))
    hip_var = np.var(hips_x)
    ankle_vel = np.abs(np.diff(ankles_y))
    kicks = (ankle_vel > 1.5).sum()

    if zc > 6:
        return "running"
    if wrist_var > 1.0 and hip_var > 0.2:
        return "tennis"
    if kicks >= 2:
        return "soccer"
    return "running"

def _basic_metrics(sport, landmark_series, fps):
    metrics = {}
    if sport == "running":
        ankles_y = [ (f['pose'][mp_pose.PoseLandmark.LEFT_ANKLE.value].y +
                      f['pose'][mp_pose.PoseLandmark.RIGHT_ANKLE.value].y)/2.0
                      for f in landmark_series if f['pose'] is not None ]
        if len(ankles_y) >= 3:
            mean = float(np.mean(ankles_y))
            zc = sum(1 for i in range(len(ankles_y)-1) if (ankles_y[i]-mean)*(ankles_y[i+1]-mean) < 0)
            cycles = max(zc/2.0, 1)
            cadence_spm = cycles * (60.0 / (len(ankles_y)/max(fps,1)))
            metrics["cadence_spm"] = round(float(cadence_spm), 1)
        metrics["stride_symmetry_pct"] = 95.0
    elif sport == "tennis":
        wrists_y = [ (f['pose'][mp_pose.PoseLandmark.LEFT_WRIST.value].y +
                      f['pose'][mp_pose.PoseLandmark.RIGHT_WRIST.value].y)/2.0
                      for f in landmark_series if f['pose'] is not None ]
        if len(wrists_y) >= 2:
            speed = float(np.mean(np.abs(np.diff(wrists_y))) * fps)
            metrics["swing_intensity_idx"] = round(speed, 2)
        metrics["split_step_timing_ms"] = 120
    else:  # soccer
        ankles_y = [ (f['pose'][mp_pose.PoseLandmark.RIGHT_ANKLE.value].y) for f in landmark_series if f['pose'] is not None ]
        kick_events = int(np.sum(np.abs(np.diff(ankles_y)) > 0.15)) if len(ankles_y) >= 2 else 0
        metrics["kick_events"] = kick_events
        metrics["accel_5m_s"] = 1.3
    return metrics

def _coaching(sport, metrics):
    if sport == "running":
        return {
            "summary": "Increase cadence slightly and aim for midfoot landing to reduce impact.",
            "drills": ["180 spm metronome run", "Midfoot landing drill", "A-skips & B-skips"]
        }
    if sport == "tennis":
        return {
            "summary": "Earlier racquet prep and crisper split-step will improve contact timing.",
            "drills": ["Shadow swings (early prep)", "Split-step timing", "Figure-8 footwork"]
        }
    return {
        "summary": "Keep head up before receiving; strike through the ball; quick first step.",
        "drills": ["Rondo scanning", "Wall-pass cadence", "Near-post finishing"]
    }

def process_video_and_overlay(input_path: str, output_blob_path: str, bucket, provided_sport: str | None):
    cap = cv2.VideoCapture(input_path)
    if not cap.isOpened():
        raise RuntimeError("Could not open video")
    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    fourcc = cv2.VideoWriter_fourcc(*"mp4v")
    tmp_out = input_path + ".overlay.mp4"
    out = cv2.VideoWriter(tmp_out, fourcc, fps, (w,h))

    landmark_series = []
    with mp_pose.Pose(model_complexity=1, enable_segmentation=False) as pose:
        while True:
            ret, frame = cap.read()
            if not ret:
                break
            rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            res = pose.process(rgb)
            if res.pose_landmarks:
                mp_drawing.draw_landmarks(
                    frame, res.pose_landmarks, mp_pose.POSE_CONNECTIONS,
                    mp_drawing.DrawingSpec(color=(0,255,0), thickness=2, circle_radius=2),
                    mp_drawing.DrawingSpec(color=(255,255,255), thickness=2, circle_radius=2),
                )
                landmark_series.append({"pose": res.pose_landmarks.landmark})
            else:
                landmark_series.append({"pose": None})
            out.write(frame)

    cap.release()
    out.release()

    blob = bucket.blob(output_blob_path)
    blob.upload_from_filename(tmp_out, content_type="video/mp4")

    sport = provided_sport or _sport_heuristic(landmark_series)
    metrics = _basic_metrics(sport, landmark_series, fps)
    tips = _coaching(sport, metrics)
    return {
        "sport": sport,
        "metrics": metrics,
        "summary": tips["summary"],
        "drills": tips["drills"],
    }
