"""
generate_prompts.py

把 annotate_arcs.py 產出的標註 JSON（結構化音樂語意標籤），
轉換成 Suno customMode 的 style 欄位文字，並標出每個弧段該用
generate（第一段）還是 extend（後續段，含 continueAt 時間點）。

規則式轉換，不需要訓練、不需要呼叫LLM。

使用方式：
    python3 generate_prompts.py annotated.json --out prompts.json
"""

import json
import argparse

TONAL_PHRASE = {
    "major": "major key",
    "minor": "minor key",
    "neutral": "ambiguous tonality",
}


def arc_to_style_prompt(labels, is_first_arc):
    tags = []

    # persist_tags 放最前面，是延續前段的核心元素，Suno在extend時最容易照著開頭的描述走
    if not is_first_arc:
        tags += labels.get("persist_tags", [])

    for t in labels.get("genre_tags", []):
        if t not in tags:
            tags.append(t)
    for t in labels.get("mood_tags", []):
        if t not in tags:
            tags.append(t)
    for t in labels.get("instrument_tags", []):
        if t not in tags:
            tags.append(t)

    tonal = labels.get("tonal_hint", "")
    if tonal in TONAL_PHRASE and TONAL_PHRASE[tonal] not in tags:
        tags.append(TONAL_PHRASE[tonal])

    for extra in ["instrumental", "cinematic"]:
        if extra not in tags:
            tags.append(extra)

    # 標籤內底線轉空格（例如 soft_piano -> soft piano），符合Suno慣用寫法
    tags = [t.replace("_", " ") for t in tags]

    return ", ".join(tags)


def build_generation_plan(annotated_data):
    arcs = annotated_data["arcs"]
    plan = []
    for i, arc in enumerate(arcs):
        is_first = (i == 0)
        style = arc_to_style_prompt(arc["labels"], is_first_arc=is_first)
        entry = {
            "arc_id": arc["arc_id"],
            "start_time_sec": arc["start_time_sec"],
            "end_time_sec": arc["end_time_sec"],
            "api_call": "generate" if is_first else "extend",
            "continue_at_sec": None if is_first else arc["start_time_sec"],
            "style": style,
            "tag_count": len(style.split(", ")),
        }
        plan.append(entry)
    return plan


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("annotated_json_path")
    parser.add_argument("--out", default="prompts.json")
    args = parser.parse_args()

    with open(args.annotated_json_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    plan = build_generation_plan(data)

    with open(args.out, "w", encoding="utf-8") as f:
        json.dump({"video_id": data.get("video_id", ""), "generation_plan": plan},
                   f, ensure_ascii=False, indent=2)

    print(f"共產生 {len(plan)} 個弧段的 prompt，已存到 {args.out}\n")
    for entry in plan:
        print(f"[{entry['arc_id']}] {entry['start_time_sec']}s-{entry['end_time_sec']}s "
              f"({entry['api_call']}, tags={entry['tag_count']})")
        print(f"  style: {entry['style']}\n")


if __name__ == "__main__":
    main()
