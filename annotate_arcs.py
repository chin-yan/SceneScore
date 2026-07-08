"""
annotate_arcs.py

讀取 group_into_arcs.py 產出的 arcs_skeleton.json，
用命令列選單引導人工標註每個弧段的 scene_features 與 labels，
標籤限定在固定詞彙表內選，避免自由輸入造成訓練資料不一致。

使用方式：
    python3 annotate_arcs.py arcs_skeleton.json --out annotated.json
"""

import json
import argparse

# 固定詞彙表（對應規格書 v2 第 6.3 節，可依需要增修）
MOOD_TAGS = ["peaceful", "epic", "melancholic", "warm", "mysterious", "dreamy",
             "tense", "uplifting", "calm", "cool", "quiet", "hopeful", "anticipatory"]
GENRE_TAGS = ["ambient", "cinematic", "lo-fi", "orchestral", "electronic", "acoustic"]
INSTRUMENT_TAGS = ["piano", "soft_piano", "strings", "low_strings", "synth_pad",
                    "acoustic_guitar", "choir", "percussion"]
TONAL_HINTS = ["major", "minor", "neutral"]
TRANSITION_TYPES = ["initial", "gradual", "distinct"]
TIME_OF_DAY = ["night", "pre_dawn", "blue_hour", "dawn", "sunrise", "day", "sunset", "dusk"]


def multi_select(prompt, options):
    print(f"\n{prompt}")
    for i, opt in enumerate(options, 1):
        print(f"  {i}. {opt}")
    raw = input("輸入編號，多選用逗號分隔（例如 1,3,5）: ").strip()
    if not raw:
        return []
    idxs = [int(x.strip()) for x in raw.split(",") if x.strip().isdigit()]
    return [options[i - 1] for i in idxs if 1 <= i <= len(options)]


def single_select(prompt, options, default=None):
    print(f"\n{prompt}")
    for i, opt in enumerate(options, 1):
        print(f"  {i}. {opt}")
    default_str = f"（直接按 Enter 用預設值 '{default}'）" if default else ""
    raw = input(f"輸入編號{default_str}: ").strip()
    if not raw and default:
        return default
    if raw.isdigit() and 1 <= int(raw) <= len(options):
        return options[int(raw) - 1]
    return default or ""


def free_text_list(prompt):
    raw = input(f"{prompt}（用逗號分隔，可留空）: ").strip()
    return [x.strip() for x in raw.split(",") if x.strip()]


def annotate_arc(arc, prev_arc, is_first):
    print("\n" + "=" * 60)
    print(f"弧段 {arc['arc_id']}  時間 {arc['start_time_sec']}s - {arc['end_time_sec']}s")
    cf = arc["features"]["color_features"]
    print(f"亮度範圍: {cf['avg_brightness_range']}  色溫範圍: {cf['color_temperature_range']}  飽和度範圍: {cf['saturation_avg_range']}")
    print(f"請先打開這張代表幀圖片: {cf['representative_frame']}")
    input("看完按 Enter 繼續...")

    # --- 場景/物件特徵 ---
    scene_category = input("\n場景類別 scene_category（自由輸入，例如 mountain / ocean / forest）: ").strip()
    time_of_day = single_select("時段 time_of_day：", TIME_OF_DAY)
    object_tags = free_text_list("物件/元素 object_tags")

    # --- 音樂語意標籤 ---
    mood_tags = multi_select("情緒標籤 mood_tags：", MOOD_TAGS)
    genre_tags = multi_select("風格標籤 genre_tags：", GENRE_TAGS)
    instrument_tags = multi_select("樂器標籤 instrument_tags：", INSTRUMENT_TAGS)
    tonal_hint = single_select("調性傾向 tonal_hint：", TONAL_HINTS)

    if is_first:
        transition_type = "initial"
        persist_tags = []
        print("\n(第一個弧段，transition_type 固定為 initial，persist_tags 為空)")
    else:
        transition_type = single_select("與前一弧段的關係 transition_type：", TRANSITION_TYPES)
        carry_candidates = list(set(prev_arc["labels"]["instrument_tags"] + prev_arc["labels"]["mood_tags"]))
        if carry_candidates:
            persist_tags = multi_select(
                f"要延續前一弧段的哪些標籤？（前段有: {carry_candidates}）", carry_candidates
            )
        else:
            persist_tags = []

    arc["features"]["scene_features"]["scene_category"] = scene_category
    arc["features"]["scene_features"]["time_of_day"] = time_of_day
    arc["features"]["scene_features"]["object_tags"] = object_tags
    arc["labels"] = {
        "mood_tags": mood_tags,
        "genre_tags": genre_tags,
        "instrument_tags": instrument_tags,
        "tonal_hint": tonal_hint,
        "transition_type": transition_type,
        "persist_tags": persist_tags,
    }
    return arc


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("arcs_skeleton_path")
    parser.add_argument("--out", default="annotated.json")
    args = parser.parse_args()

    with open(args.arcs_skeleton_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    prev_arc = None
    for i, arc in enumerate(data["arcs"]):
        data["arcs"][i] = annotate_arc(arc, prev_arc, is_first=(i == 0))
        prev_arc = data["arcs"][i]

    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    print(f"\n全部弧段標註完成，已存到 {args.out}")


if __name__ == "__main__":
    main()
