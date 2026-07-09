"""
run_pipeline.py

整合 extract_features.py -> group_into_arcs.py -> annotate_arcs.py -> generate_prompts.py
四個步驟，一次執行完整流程。所有輸出檔案（frames、features.json、arcs_skeleton.json、
annotated.json、prompts.json）都會放在同一個以影片檔名命名的資料夾內。

使用方式：
    python3 run_pipeline.py <影片路徑> --interval 1 --min_arc_duration 6

只想跑到特徵萃取+弧段分組，先不進入互動標註（例如想先批次處理多支影片的特徵）：
    python3 run_pipeline.py <影片路徑> --no-annotate
"""

import argparse
import subprocess
import sys
import os


def run_step(description, cmd):
    print(f"\n{'=' * 60}\n{description}\n{'=' * 60}")
    result = subprocess.run(cmd)
    if result.returncode != 0:
        print(f"\n[錯誤] 這個步驟失敗了：{' '.join(cmd)}")
        sys.exit(result.returncode)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("video_path")
    parser.add_argument("--interval", type=float, default=1.0, help="取樣間隔（秒）")
    parser.add_argument("--min_arc_duration", type=float, default=15.0)
    parser.add_argument("--outdir", default=None,
                         help="所有輸出檔案的根資料夾，預設為 <影片檔名>/")
    parser.add_argument("--no-annotate", action="store_true",
                         help="只跑到弧段分組，不進入互動標註")
    args = parser.parse_args()

    # 取影片檔名（不含副檔名）當作資料夾名稱，這支影片產生的所有檔案都放這裡面
    video_stem = os.path.splitext(os.path.basename(args.video_path))[0]
    root = args.outdir if args.outdir else f"./{video_stem}"
    os.makedirs(root, exist_ok=True)

    frames_outdir = os.path.join(root, "frames")
    features_out = os.path.join(root, "features.json")
    skeleton_out = os.path.join(root, "arcs_skeleton.json")
    annotated_out = os.path.join(root, "annotated.json")
    prompts_out = os.path.join(root, "prompts.json")

    print(f"影片: {video_stem}")
    print(f"輸出資料夾: {root}/")
    print(f"  frames     → {frames_outdir}")
    print(f"  features   → {features_out}")
    print(f"  skeleton   → {skeleton_out}")
    print(f"  annotated  → {annotated_out}")
    print(f"  prompts    → {prompts_out}")

    script_dir = os.path.dirname(os.path.abspath(__file__))
    py = sys.executable

    # Step 1: 特徵萃取
    run_step(
        "Step 1/4　特徵萃取（色彩/光影特徵 + 候選弧段邊界）",
        [py, os.path.join(script_dir, "extract_features.py"), args.video_path,
         "--interval", str(args.interval),
         "--outdir", frames_outdir,
         "--min_arc_duration", str(args.min_arc_duration),
         "--features_out", features_out]
    )

    # Step 2: 弧段分組
    run_step(
        "Step 2/4　弧段分組彙整",
        [py, os.path.join(script_dir, "group_into_arcs.py"), features_out,
         "--out", skeleton_out]
    )

    if args.no_annotate:
        print(f"\n已完成到弧段分組，{skeleton_out} 已產生。"
              f"\n若要繼續人工標註，稍後執行：\n"
              f"  python3 annotate_arcs.py {skeleton_out} --out {annotated_out}")
        return

    # Step 3: 互動式標註
    run_step(
        "Step 3/4　人工標註（互動式選單）",
        [py, os.path.join(script_dir, "annotate_arcs.py"), skeleton_out,
         "--out", annotated_out]
    )

    # Step 4: 產生 Suno prompt
    run_step(
        "Step 4/4　轉換成 Suno style prompt",
        [py, os.path.join(script_dir, "generate_prompts.py"), annotated_out,
         "--out", prompts_out]
    )

    print(f"\n全部完成！標註結果 → {annotated_out}，Suno prompt → {prompts_out}")


if __name__ == "__main__":
    main()