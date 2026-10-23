import os
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")

DATA_DIR = ROOT / "data"
LOG_DIR = ROOT / "logs"
RECORDINGS_DIR = ROOT / "recordings"
DB_PATH = DATA_DIR / "stats.db"
WORDS_PATH = DATA_DIR / "詞庫.txt"
WORDS_EXAMPLE_PATH = DATA_DIR / "詞庫.範例.txt"
SYNONYMS_PATH = DATA_DIR / "同義規則.txt"
SYNONYMS_EXAMPLE_PATH = DATA_DIR / "同義規則.範例.txt"

HOST = "127.0.0.1"
PORT = int(os.getenv("SERVICE_PORT", "8765"))

WHISPER_MODEL = os.getenv("WHISPER_MODEL", "large-v3-turbo")
WHISPER_DEVICE = os.getenv("WHISPER_DEVICE", "cuda")
# 留空代表自動偵測語言
WHISPER_LANGUAGE = os.getenv("WHISPER_LANGUAGE", "zh") or None

# 測試收音用：設為 1 會把每段聲音存到 recordings/，平常請保持 0
SAVE_AUDIO = os.getenv("SAVE_AUDIO", "0") == "1"
