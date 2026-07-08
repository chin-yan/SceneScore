# 標註資料前處理工具 - 使用說明

對應規格書：《視覺轉音樂語意對應層 專案規格書 v2》

## 完整流程

```
extract_features.py   → features.json（逐幀色彩特徵 + 候選弧段邊界，全自動）
        ↓
group_into_arcs.py    → arcs_skeleton.json（依邊界分組彙整，labels留空，全自動）
        ↓
annotate_arcs.py       → annotated.json（互動式選單標註，人工判斷）
```

## 1. extract_features.py

```bash
python3 extract_features.py <影片路徑> --interval 1 --outdir ./frames --min_arc_duration 6
```

- `--interval`：取樣間隔（秒）
- `--min_arc_duration`：弧段最短時長（秒）
- `--outdir`：關鍵幀輸出資料夾

輸出 `features.json`（逐幀色彩特徵 + 候選弧段邊界）。

若影片路徑錯誤或 ffprobe 讀取失敗，會直接印出具體錯誤原因，不會再是看不懂的 ValueError。

## 2. group_into_arcs.py

```bash
python3 group_into_arcs.py features.json --out arcs_skeleton.json
```

把 `features.json` 依候選邊界分組，算出每個弧段的色彩特徵範圍與代表幀（弧段中間那一幀），
`scene_features` 與 `labels` 留空，等待人工填寫。

## 3. annotate_arcs.py

```bash
python3 annotate_arcs.py arcs_skeleton.json --out annotated.json
```

互動式命令列工具，依序帶你標註每個弧段：

1. 先印出代表幀圖片路徑，請自行打開圖片查看
2. 場景類別、時段、物件標籤（time_of_day 有選單，scene_category/object_tags 為自由輸入）
3. mood_tags / genre_tags / instrument_tags 從固定詞彙表選（可多選）
4. tonal_hint 單選
5. 非第一個弧段時，會列出前一弧段的標籤讓你勾選哪些要延續（persist_tags），並選 transition_type

標籤詞彙表寫死在檔案開頭（`MOOD_TAGS`、`GENRE_TAGS`、`INSTRUMENT_TAGS` 等常數），
若要增修詞彙表，直接改這幾個 list 即可，不用改其他邏輯。

## 場景/物件辨識目前仍是人工判斷

還沒接 CLIP 或 Places365 之類的自動場景分類模型，`scene_category` 目前是自由輸入文字，
之後如果要跟 mood_tags 一樣做規範化的多標籤分類，建議先累積一批標註資料，
統計出常出現的場景詞彙，再收斂成固定詞彙表。

## 音樂語意標籤 → Suno prompt

這一步不需要訓練、不需要標註，是規則式函式（見對話紀錄中的 `arc_to_style_prompt`），
把標註好的標籤直接拼接成 Suno 的 style 欄位文字。之後可以視需要另外整理成
`generate_prompts.py`，這支檔案還沒建立。
