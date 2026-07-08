# 視覺→音樂語意對應層 專案規格書 v2

> v2 變更重點：加入「時間弧段（arc）」機制，解決單一靜態 prompt 無法反映畫面隨時間演變（如日出前後）的問題。輸出從「整段影片一組標籤」改為「弧段序列」，並新增與 Suno generate/extend API 對應的生成策略。

## 1. 專案目標

訓練一個輕量模型，輸入為縮時攝影影片的「色彩/光影特徵」與「場景/物件辨識特徵」（依時間切成多個弧段），輸出為**隨時間演變的結構化音樂語意標籤序列**，並可組合成 Suno 可用的 prompt 序列，透過 generate + extend 串接生成一首會隨畫面變化的完整配樂。

## 2. 範圍界定

| 特徵類別 | 是否納入本階段 |
|---|---|
| 色彩 / 光影特徵 | ✅ 納入 |
| 場景 / 物件辨識特徵 | ✅ 納入 |
| 動態 / 節奏特徵（雲速、光影變化速度） | ❌ 下一階段再擴充 |

輸出範圍：每個弧段一組結構化音樂語意標籤 + 弧段間的轉換描述，不含 tempo/BPM 精確數值。

## 3. 核心概念：弧段（Arc）與場景切分的差異

**場景切分**回答的問題是「畫面構圖/鏡頭什麼時候變了」。
**弧段切分**回答的問題是「音樂情緒什麼時候該變了」。

兩者不是同一件事。日出縮時的色彩、亮度是連續漸變的，可能完全沒有明顯鏡頭切點，但音樂仍需要在某個時刻開始轉變。因此弧段切分需要獨立的邏輯：

- 對色彩特徵（`avg_brightness`、`color_temperature`、`saturation_avg`）做滑動視窗，計算隨時間的**累積變化量**（而非相鄰幀的瞬時差異）
- 當累積變化量超過閾值，且持續一段最短時間（避免雜訊造成頻繁誤判），標記為一個新弧段的起點
- 場景切分的邊界可作為候選參考點，但不是唯一依據

**弧段最短時長**建議設一個下限（例如 15-20 秒），避免過度切分導致音樂變化過於瑣碎、且增加不必要的 API 呼叫成本。

## 4. 輸入特徵規格

### 4.1 色彩 / 光影特徵（每個弧段一筆，並保留弧段內的時間序列供切分演算法使用）

| 欄位 | 說明 | 型態 |
|---|---|---|
| `dominant_colors` | 弧段內前 5 大主色（HSV，取弧段中段代表幀） | array[5] of [h,s,v] |
| `avg_brightness` | 弧段平均亮度 | float 0-1 |
| `contrast` | 對比度 | float 0-1 |
| `color_temperature` | 冷暖傾向 | float -1~1 |
| `saturation_avg` | 平均飽和度 | float 0-1 |
| `brightness_delta_within` | 弧段內部亮度變化幅度 | float |
| `brightness_delta_from_prev_arc` | 與前一弧段的亮度差 | float |
| `color_temp_delta_from_prev_arc` | 與前一弧段的色溫差 | float |

> 最後兩個欄位是 v2 新增，專門用來讓模型判斷「這個弧段相對前一段變化有多大」，作為 `transition_type` 判斷的依據。

### 4.2 場景 / 物件辨識特徵

| 欄位 | 說明 | 型態 |
|---|---|---|
| `scene_category` | 主場景類別 | string |
| `scene_confidence` | 分類信心值 | float 0-1 |
| `object_tags` | 偵測到的物件/元素 | array[string] |
| `time_of_day` | 推測時段（sunrise, day, sunset, night，可含 transitional 標記如 pre_sunrise） | string |

### 4.3 弧段特徵記錄範例

```json
{
  "arc_id": "arc_02",
  "start_time_sec": 45,
  "end_time_sec": 90,
  "color_features": {
    "dominant_colors": [[25,0.6,0.9],[10,0.8,0.7],[200,0.3,0.4],[40,0.5,0.6],[0,0.1,0.95]],
    "avg_brightness": 0.55,
    "contrast": 0.5,
    "color_temperature": 0.2,
    "saturation_avg": 0.45,
    "brightness_delta_within": 0.28,
    "brightness_delta_from_prev_arc": 0.33,
    "color_temp_delta_from_prev_arc": 0.5
  },
  "scene_features": {
    "scene_category": "mountain",
    "scene_confidence": 0.85,
    "object_tags": ["clouds", "horizon", "sun_glow"],
    "time_of_day": "pre_sunrise"
  }
}
```

## 5. 輸出規格

### 5.1 單一弧段的結構化音樂語意標籤

| 欄位 | 說明 | 型態 |
|---|---|---|
| `mood_tags` | 情緒標籤（可多選） | array[string] |
| `genre_tags` | 風格標籤 | array[string] |
| `instrument_tags` | 建議樂器 | array[string] |
| `tonal_hint` | 調性傾向 | string（major/minor/neutral） |
| `transition_type` | 與前一弧段的關係 | string（`gradual` 漸變 / `distinct` 明顯轉折 / `initial` 第一段無前段） |
| `persist_tags` | 從前一弧段延續、不應改變的標籤（用於對抗 Suno extend 的風格漂移） | array[string] |

### 5.2 全片輸出格式：弧段標籤序列

```json
{
  "video_id": "sunrise_001",
  "arcs": [
    {
      "arc_id": "arc_01",
      "start_time_sec": 0,
      "end_time_sec": 45,
      "labels": {
        "mood_tags": ["mysterious", "cool"],
        "genre_tags": ["ambient"],
        "instrument_tags": ["synth_pad", "strings"],
        "tonal_hint": "minor",
        "transition_type": "initial",
        "persist_tags": []
      }
    },
    {
      "arc_id": "arc_02",
      "start_time_sec": 45,
      "end_time_sec": 90,
      "labels": {
        "mood_tags": ["hopeful", "warming"],
        "genre_tags": ["ambient", "cinematic"],
        "instrument_tags": ["synth_pad", "strings", "piano"],
        "tonal_hint": "neutral",
        "transition_type": "gradual",
        "persist_tags": ["synth_pad", "strings"]
      }
    },
    {
      "arc_id": "arc_03",
      "start_time_sec": 90,
      "end_time_sec": 150,
      "labels": {
        "mood_tags": ["uplifting", "warm"],
        "genre_tags": ["cinematic"],
        "instrument_tags": ["piano", "strings", "choir"],
        "tonal_hint": "major",
        "transition_type": "gradual",
        "persist_tags": ["strings", "piano"]
      }
    }
  ]
}
```

## 6. 音樂生成串接策略（Suno generate + extend）

1. **第一個弧段**：用 `generate` API，prompt 由 arc_01 的標籤組成
2. **後續每個弧段**：用 `extend` API，`continueAt` 設為前一弧段的結束時間，prompt 由「新弧段標籤 + persist_tags 重新聲明」組成，明確告知哪些元素延續、哪些情緒改變
3. `transition_type = distinct` 時，可以放寬讓 extend 的 style 參數做較大幅度調整；`transition_type = gradual` 時，prompt 應強調「維持大部分元素，只做漸進式演變」，並在 style_weight／weirdness 等參數上偏保守，降低風格漂移風險
4. 全部弧段生成完後，用 `Get Whole Song`（或等效串接）合併成一首連續配樂
5. **已知風險**：extend 多次串接後容易產生風格漂移（曲風、人聲、節奏偏移），需要在每次呼叫都完整重複 persist_tags，並在小範圍測試中觀察漂移程度，必要時限制單一影片最多允許幾次 extend 串接

## 7. 模型架構

延續 v1 的多標籤分類設計，但需處理弧段間的**序列相依性**（後一弧段的標籤會受前一弧段影響，例如 persist_tags 直接依賴前一弧段的輸出）：

- **每弧段獨立特徵**：色彩 + 場景特徵（同 v1）
- **序列脈絡輸入**：額外把「前一弧段的標籤輸出」與「與前一弧段的特徵差值」（`brightness_delta_from_prev_arc` 等）一併輸入
- **模型本體**：輕量序列模型（如單層 GRU/LSTM，或簡化為「MLP + 前一步輸出當作額外特徵」的自回歸方式，不必一開始就上 Transformer，資料量不足時容易過擬合）
- **輸出頭**：mood / genre / instrument / tonal 四個分類頭（同 v1）+ 新增 transition_type 分類頭（三分類）+ persist_tags（可先用規則：與前一弧段標籤的交集 + 模型信心高的部分，不一定要模型直接生成，先用規則版本上線，之後再評估是否要模型化）

## 8. 訓練資料規格

### 8.1 標註 schema

在 v1 的基礎上，標註時**以整支影片為單位**，而非單一片段獨立標註——因為 transition_type 和 persist_tags 需要標註者同時看過前後弧段才能判斷，標註介面需要能呈現弧段序列脈絡。

```json
{
  "video_id": "sunrise_001",
  "arcs": [
    { "arc_id": "arc_01", "features": {...}, "labels": {...} },
    { "arc_id": "arc_02", "features": {...}, "labels": {...} }
  ]
}
```

### 8.2 資料來源策略

同 v1（弱監督反推既有配樂縮時影片、人工標註、規則輔助冷啟動），但標註工作量因為要標「弧段切分點＋序列標籤」而提高，建議：

- 先用第 3 節的規則式弧段切分演算法自動產生候選切點，人工只需要「確認/調整切點」而非從頭標記，降低標註成本
- 優先挑選畫面變化明顯的影片（日出、日落、天氣轉變）作為早期標註素材，這類影片的弧段轉折最清楚，有助於模型先學會「大轉折」再處理「細膩漸變」

### 8.3 標籤詞彙表

同 v1（見附錄），新增 `transition_type` 固定三分類：`initial` / `gradual` / `distinct`。

## 9. 評估方式

- **量化指標**：同 v1 的分類指標（F1、accuracy），額外加上 transition_type 的分類準確率
- **序列一致性檢查**：檢查模型輸出的 persist_tags 是否與前一弧段標籤有合理重疊（規則化的一致性檢查，非單純分類指標）
- **端到端驗證（本階段最重要）**：實際跑 generate → extend 串接生成音樂，人工評分兩件事分開看——（a）單一弧段的音樂是否符合該段畫面情緒（b）弧段銜接處是否自然、有沒有明顯風格漂移或斷裂感

## 10. 里程碑規劃

| 階段 | 內容 | 產出 |
|---|---|---|
| M1 | 特徵萃取 pipeline（含弧段切分演算法） | 可輸出弧段序列特徵 |
| M2 | 標籤詞彙表定案 + 弧段切分校正介面 + 標註 15-20 支完整影片 | 標註資料集 v0（序列格式） |
| M3 | 序列模型訓練（MLP+前步輸出 或 輕量 GRU） | 模型 v0 + 分類指標報告 |
| M4 | Suno generate/extend 串接測試 | 完整配樂樣本，含銜接處人工評分 |
| M5 | 依銜接處評分結果，調整 persist_tags 規則與 prompt 模板 | 模型 v1 + 生成策略 v1 |
| M6 | 擴充資料、迭代 | 模型 v2 |

## 11. 風險與待決問題

- 弧段切分閾值（多大的累積變化算「該換音樂」）目前只能先設經驗值，需要在 M2 標註階段用真實案例校準
- extend 串接次數增加時風格漂移會累積，需要實測抓出「安全串接上限」，超過上限的長影片可能需要考慮分段生成後手動剪接，而非全程用 extend
- persist_tags 先用規則版本上線是刻意簡化，若後續發現規則版效果不好（銜接生硬或跳躍過大），才需要投入訓練資料把它變成模型輸出
- 標註工作量比 v1 高（需要看過整支影片脈絡），要重新評估標註時間預算是否足夠支撐 M2 的資料量目標
- 本階段仍未納入動態特徵（雲速等），若 M4 端到端測試發現「有些轉折光靠色彩/場景判斷不出該不該換音樂」，可能需要提前引入動態特徵到弧段切分邏輯中
