"""
extract_features.py

依照《視覺轉音樂語意對應層 專案規格書 v2》第4節規格，
從縮時攝影影片萃取色彩/光影特徵，並依第3節規則產生候選弧段切分點。

使用方式：
    python3 extract_features.py <影片路徑> [--interval 2] [--outdir ./frames]

輸出：
    - <outdir>/frame_XXXX.jpg：每個取樣時間點的關鍵幀（供人工判斷場景/物件用）
    - features.json：每個取樣點的色彩特徵 + 候選弧段切分點
"""

import cv2
import numpy as np
import json
import subprocess
import argparse
import os


def get_video_duration(video_path):
    if not os.path.exists(video_path):
        raise FileNotFoundError(f"找不到影片檔案: {video_path}（確認路徑和檔名是否正確）")
    result = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=noprint_wrappers=1:nokey=1", video_path],
        capture_output=True, text=True
    )
    if result.returncode != 0 or not result.stdout.strip():
        raise RuntimeError(
            f"ffprobe 讀取影片失敗。\nstderr: {result.stderr.strip()}\n"
            f"可能原因：影片檔案損壞、格式不支援，或 ffprobe 版本有問題。"
        )
    return float(result.stdout.strip())


def extract_frames(video_path, outdir, interval_sec):
    os.makedirs(outdir, exist_ok=True)
    duration = get_video_duration(video_path)
    timestamps = np.arange(0, duration, interval_sec)
    frame_paths = []
    for i, t in enumerate(timestamps):
        out_path = os.path.join(outdir, f"frame_{i:04d}_t{t:.1f}s.jpg")
        subprocess.run(
            ["ffmpeg", "-y", "-ss", str(t), "-i", video_path,
             "-frames:v", "1", "-q:v", "2", out_path],
            capture_output=True
        )
        if os.path.exists(out_path):
            frame_paths.append({"time_sec": float(t), "path": out_path})
    return frame_paths, duration


def compute_color_features(frame_path, k=5):
    img = cv2.imread(frame_path)
    if img is None:
        return None
    img_rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
    img_hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
    img_gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

    # 下採樣加速 k-means
    small_hsv = cv2.resize(img_hsv, (80, 45)).reshape(-1, 3).astype(np.float32)
    from sklearn.cluster import KMeans
    km = KMeans(n_clusters=k, n_init=3, random_state=0).fit(small_hsv)
    counts = np.bincount(km.labels_)
    order = np.argsort(-counts)
    dominant_colors = km.cluster_centers_[order].tolist()  # [[h,s,v], ...] 0-255 scale

    avg_brightness = float(np.mean(img_gray)) / 255.0
    contrast = float(np.std(img_gray)) / 255.0
    saturation_avg = float(np.mean(img_hsv[:, :, 1])) / 255.0

    r_mean = float(np.mean(img_rgb[:, :, 0]))
    b_mean = float(np.mean(img_rgb[:, :, 2]))
    color_temperature = (r_mean - b_mean) / (r_mean + b_mean + 1e-6)  # -1(冷) ~ 1(暖)

    return {
        "dominant_colors": dominant_colors,
        "avg_brightness": round(avg_brightness, 4),
        "contrast": round(contrast, 4),
        "color_temperature": round(color_temperature, 4),
        "saturation_avg": round(saturation_avg, 4),
    }


def detect_arc_boundaries(features_series, min_arc_duration=15,
                            brightness_threshold=0.15, color_temp_threshold=0.2):
    """
    依累積變化量偵測候選弧段邊界（規格書第3節邏輯）。
    以上一個邊界點為基準，累積亮度/色溫變化超過閾值，且距離上個邊界超過最短時長，才標記新邊界。
    """
    boundaries = [0]  # 第一個弧段一定從t=0開始
    ref_idx = 0
    for i in range(1, len(features_series)):
        t = features_series[i]["time_sec"]
        last_boundary_t = features_series[boundaries[-1]]["time_sec"]
        if t - last_boundary_t < min_arc_duration:
            continue
        b_delta = abs(features_series[i]["color_features"]["avg_brightness"] -
                      features_series[ref_idx]["color_features"]["avg_brightness"])
        c_delta = abs(features_series[i]["color_features"]["color_temperature"] -
                      features_series[ref_idx]["color_features"]["color_temperature"])
        if b_delta >= brightness_threshold or c_delta >= color_temp_threshold:
            boundaries.append(i)
            ref_idx = i
    return boundaries


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("video_path")
    parser.add_argument("--interval", type=float, default=2.0, help="取樣間隔（秒）")
    parser.add_argument("--outdir", default="./frames")
    parser.add_argument("--min_arc_duration", type=float, default=15.0)
    parser.add_argument("--features_out", default="features.json",
                         help="輸出的特徵JSON檔名，預設 features.json")
    args = parser.parse_args()

    frame_infos, duration = extract_frames(args.video_path, args.outdir, args.interval)
    print(f"影片長度: {duration:.1f}s，取樣 {len(frame_infos)} 張關鍵幀")

    features_series = []
    for fi in frame_infos:
        cf = compute_color_features(fi["path"])
        if cf is None:
            continue
        features_series.append({
            "time_sec": fi["time_sec"],
            "frame_path": fi["path"],
            "color_features": cf
        })

    boundary_indices = detect_arc_boundaries(features_series, min_arc_duration=args.min_arc_duration)
    boundary_times = [features_series[i]["time_sec"] for i in boundary_indices]

    output = {
        "video_path": args.video_path,
        "duration_sec": duration,
        "sample_interval_sec": args.interval,
        "candidate_arc_boundaries_sec": boundary_times,
        "features_series": features_series,
    }

    with open(args.features_out, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    print(f"候選弧段邊界（秒）: {boundary_times}")
    print(f"特徵與候選邊界已存到 {args.features_out}")


if __name__ == "__main__":
    main()