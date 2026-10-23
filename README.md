# dc_mom_counter

在私人 Discord 伺服器的語音頻道裡，統計每個人說出「媽媽系列」髒話的次數，並用斜線指令叫出排行榜。

- 語音辨識在你自己的電腦上跑（faster-whisper，使用顯示卡），不用付費、不上傳雲端
- 只有你下 `/開始` 時才收音與計時，`/結束` 就停止（碼表式累計）
- 詞庫與同義規則可以在機器人上線時隨時用指令新增
- 每次偵測都會寫進每週一個的 CSV 紀錄檔（`logs/2026-W43.csv`），可用 Excel 開啟

## 架構

```
Discord 語音頻道 ──音訊、指令──▶ Node.js（bot/）──音檔、指令──▶ Python（service/）
                ◀──回覆訊息──                  ◀──統計結果──    Whisper → 詞庫比對 → SQLite / CSV
```

Node.js 只負責登入 Discord、收音、轉送指令（Python 目前沒有能穩定解密 Discord 語音加密 DAVE 的套件）；辨識、比對、排行榜都在 Python。

## 一、事前準備（只需要做一次）

### 1. 安裝軟體

- [Node.js 22 LTS](https://nodejs.org/)
- [Python 3.12](https://www.python.org/downloads/)（安裝時勾選「Add python.exe to PATH」）
- 顯示卡驅動請更新到最新版（RTX 4060 需支援 CUDA 12）

### 2. 建立 Discord 機器人

1. 到 [Discord Developer Portal](https://discord.com/developers/applications) → **New Application**，取個名字。
2. 左邊選 **Bot** → **Reset Token** → 複製 Token（等等填到 `.env` 的 `DISCORD_TOKEN`，不要給別人看）。
3. 左邊選 **OAuth2** → 複製 **Client ID**，把下面網址的 `你的CLIENT_ID` 換掉後用瀏覽器打開，把機器人邀進你的伺服器：

   ```
   https://discord.com/oauth2/authorize?client_id=你的CLIENT_ID&scope=bot%20applications.commands&permissions=1068032
   ```

   （權限包含：檢視頻道、傳送訊息、嵌入連結、連接語音）

### 3. 取得伺服器 ID 與你的使用者 ID

Discord → 使用者設定 → 進階 → 開啟 **開發者模式**。之後：

- 在伺服器名稱上按右鍵 → **複製伺服器 ID** → `GUILD_ID`
- 在自己的頭像上按右鍵 → **複製使用者 ID** → `OWNER_ID`

### 4. 安裝

1. 在 GitHub 頁面按 **Code → Download ZIP**，解壓縮（或用 `git clone`）。
2. 雙擊 `install.bat`，等它跑完（第一次會下載不少東西）。
3. 用記事本打開 `.env`，填入 `DISCORD_TOKEN`、`GUILD_ID`、`OWNER_ID`。

## 二、使用

雙擊 `start.bat`，會開兩個視窗（Python 服務、機器人）。第一次啟動會下載語音模型（約 1.6 GB），Python 視窗顯示「Whisper 模型 … 已載入」就完成了。要關掉機器人，把兩個視窗都關掉即可。

| 指令 | 說明 | 誰能用 |
| --- | --- | --- |
| `/開始` | 機器人進入你所在的語音頻道，開始收音與計時 | 只有你 |
| `/結束` | 離開頻道，回報這次的收聽時間與次數 | 只有你 |
| `/排行榜 成員` | 誰講最多，以及每人最愛的那句 | 所有人 |
| `/排行榜 髒話` | 哪句最常出現，以及最常說的人 | 所有人 |
| `/查詢 @成員` | 某人的總次數與各句分佈 | 所有人 |
| `/狀態` | 是否收音中、累計時間、模型狀態 | 所有人 |
| `/詞庫 新增` / `刪除` / `列表` / `重新載入` | 管理要統計的句子 | 只有你 |
| `/同義 新增` / `刪除` / `列表` | 管理語助詞、錯字等同義規則 | 只有你 |

## 三、詞庫與比對規則

第一次啟動時會從範例建立 `data/詞庫.txt` 和 `data/同義規則.txt`。可以用指令改，也可以直接用記事本編輯，改完用 `/詞庫 重新載入` 套用，不用重開機器人。

**詞庫** `data/詞庫.txt`：一行一句，`=` 後面是變體（辨識可能寫出的其他寫法）。

```
你媽
你媽死了 = 你馬死了, 尼瑪死了
你M的
```

**同義規則** `data/同義規則.txt`：套用在所有句子上。

```
啦 -> 了
妳 -> 你
```

比對方式：

1. 辨識結果先簡轉繁、英文轉小寫、去掉標點。
2. 套用同義規則，所以「你媽死啦」會變成「你媽死了」。
3. 由左到右找出詞庫裡的句子，**只算最長的那句**：「你媽死了」只記一次「你媽死了」，不會另外記「你媽」。前面多了「糙」「操」之類的字也照樣算得到。
4. 英文句子會檢查單字邊界，`your mom` 不會在 `your momentum` 裡被算到。

新加的詞只從加入那一刻開始計算，不會回頭補算。

## 四、第一次使用：收音測試

Discord 從 2026 年起強制語音端對端加密（DAVE），收音是這個專案最容易出問題的地方，建議第一次先確認收得到清楚的聲音：

1. 在 `.env` 把 `SAVE_AUDIO=1`，執行 `start.bat`。
2. 進語音頻道，下 `/開始`，找朋友講幾句話，再下 `/結束`。
3. 打開 `recordings/` 資料夾，聽聽看每段 `.wav` 是否清楚、有沒有斷斷續續。
4. Python 視窗也會即時印出每句辨識結果，可以順便看辨識準不準。
5. 確認完把 `SAVE_AUDIO` 改回 `0`，並刪除 `recordings/` 資料夾。

平常（`SAVE_AUDIO=0`）聲音只在記憶體裡辨識，不會存檔。

## 五、檔案說明

| 路徑 | 內容 |
| --- | --- |
| `data/詞庫.txt`、`data/同義規則.txt` | 你的詞庫與規則 |
| `data/stats.db` | 統計資料（SQLite），刪掉等於歸零 |
| `logs/年-W週.csv` | 每週紀錄檔：時間、使用者 ID、名稱、髒話、辨識原句 |

## 六、常見問題

- **Python 視窗出現「GPU 載入失敗，改用 CPU」**：通常是顯示卡驅動太舊，請更新 NVIDIA 驅動。暫時可以在 `.env` 設 `WHISPER_DEVICE=cpu`，或換小一點的模型 `WHISPER_MODEL=small`。
- **Python 視窗直接關掉或閃退**：同上，先試 `WHISPER_DEVICE=cpu` 確認是不是顯示卡函式庫的問題。
- **指令沒出現**：確認邀請網址有包含 `applications.commands`，並重開機器人；Discord 偶爾要等一下或重新整理（Ctrl+R）。
- **英文常常沒抓到**：把 `.env` 的 `WHISPER_LANGUAGE` 留空改成自動偵測試試看。
- **某句一直漏算**：看紀錄檔或 Python 視窗裡的辨識原句，把 Whisper 實際寫出來的寫法用 `/詞庫 新增`（填在「變體」）或 `/同義 新增` 加進去。

## 開發

```
test.bat                      # Windows：跑比對與統計的測試
.venv\Scripts\python -m pytest -q service\tests
```
