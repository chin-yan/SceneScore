"""
group_into_arcs.py

把 extract_features.py 產出的 features.json（逐幀特徵 + 候選邊界）
依邊界點分組彙整成「弧段骨架」，labels 留空給人工填寫。

使用方式：
    python3 group_into_arcs.py features.json --out arcs_skeleton.json
"""

import json
import argparse


def summarize_arc(frames):
    brightness_vals = [f["color_features"]["avg_brightness"] for f in frames]
    color_temp_vals = [f["color_features"]["color_temperature"] for f in frames]
    saturation_vals = [f["color_features"]["saturation_avg"] for f in frames]
    # 取弧段中間那幀當代表幀，方便人工標場景/物件時參考
    mid_frame = frames[len(frames) // 2]
    return {
        "avg_brightness_range": [round(min(brightness_vals), 3), round(max(brightness_vals), 3)],
        "color_temperature_range": [round(min(color_temp_vals), 3), round(max(color_temp_vals), 3)],
        "saturation_avg_range": [round(min(saturation_vals), 3), round(max(saturation_vals), 3)],
        "brightness_delta_within": round(max(brightness_vals) - min(brightness_vals), 3),
        "representative_frame": mid_frame["frame_path"],
    }


def group_into_arcs(features_json_path):
    with open(features_json_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    series = data["features_series"]
    boundaries_sec = data["candidate_arc_boundaries_sec"]
    duration = data["duration_sec"]

    # 依時間找出每個弧段對應的 frame 區間
    boundary_points = boundaries_sec + [duration]
    arcs = []
    prev_summary = None
    for i in range(len(boundary_points) - 1):
        start_t, end_t = boundary_points[i], boundary_points[i + 1]
        frames_in_arc = [f for f in series if start_t <= f["time_sec"] < end_t]
        if not frames_in_arc:
            continue
        summary = summarize_arc(frames_in_arc)

        delta_from_prev = None
        color_temp_delta = None
        if prev_summary is not None:
            delta_from_prev = round(
                summary["avg_brightness_range"][0] - prev_summary["avg_brightness_range"][0], 3
            )
            color_temp_delta = round(
                summary["color_temperature_range"][0] - prev_summary["color_temperature_range"][0], 3
            )
        summary["brightness_delta_from_prev_arc"] = delta_from_prev
        summary["color_temp_delta_from_prev_arc"] = color_temp_delta

        arcs.append({
            "arc_id": f"arc_{i+1:02d}",
            "start_time_sec": round(start_t, 1),
            "end_time_sec": round(end_t, 1),
            "features": {
                "color_features": summary,
                "scene_features": {
                    "scene_category": "",       # 待人工填寫，看 representative_frame
                    "scene_confidence": None,
                    "object_tags": [],
                    "time_of_day": ""
                }
            },
            "labels": {
                "mood_tags": [],
                "genre_tags": [],
                "instrument_tags": [],
                "tonal_hint": "",
                "transition_type": "initial" if i == 0 else "",
                "persist_tags": []
            }
        })
        prev_summary = summary

    return {
        "video_id": data["video_path"].split("/")[-1].rsplit(".", 1)[0],
        "duration_sec": duration,
        "arcs": arcs
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("features_json_path")
    parser.add_argument("--out", default="arcs_skeleton.json")
    args = parser.parse_args()

    result = group_into_arcs(args.features_json_path)
    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    print(f"分出 {len(result['arcs'])} 個弧段骨架，已存到 {args.out}")
    print("請打開每個弧段的 representative_frame 圖片，人工填寫 scene_features 與 labels")


if __name__ == "__main__":
    main()
