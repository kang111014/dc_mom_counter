"""統計資料（SQLite）與每週 CSV 紀錄檔。"""

import csv
import sqlite3
import threading
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS sessions (
    id INTEGER PRIMARY KEY,
    started_at REAL NOT NULL,
    ended_at REAL,
    last_seen REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS detections (
    id INTEGER PRIMARY KEY,
    ts REAL NOT NULL,
    user_id TEXT NOT NULL,
    user_name TEXT NOT NULL,
    phrase TEXT NOT NULL,
    transcript TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_detections_user ON detections(user_id);
CREATE INDEX IF NOT EXISTS idx_detections_phrase ON detections(phrase);
"""

LOG_FIELDS = ["時間", "使用者ID", "名稱", "髒話", "辨識原句"]


class SessionError(Exception):
    pass


@dataclass
class MemberRank:
    user_id: str
    name: str
    count: int
    top_phrase: str
    top_count: int


@dataclass
class PhraseRank:
    phrase: str
    count: int
    top_user_id: str
    top_count: int


class Storage:
    def __init__(self, db_path: Path, log_dir: Path):
        db_path.parent.mkdir(parents=True, exist_ok=True)
        self.log_dir = log_dir
        self._db = sqlite3.connect(db_path, check_same_thread=False)
        self._db.executescript(SCHEMA)
        self._lock = threading.Lock()

    # ---------- 碼表 ----------

    def recover_open_sessions(self) -> None:
        """程式意外關閉時，把沒結束的那次以最後收到音訊的時間結束。"""
        with self._lock, self._db:
            self._db.execute("UPDATE sessions SET ended_at = last_seen WHERE ended_at IS NULL")

    def active_session(self):
        row = self._db.execute(
            "SELECT id, started_at FROM sessions WHERE ended_at IS NULL ORDER BY id DESC LIMIT 1"
        ).fetchone()
        return row

    def start_session(self, now: float) -> None:
        with self._lock, self._db:
            if self.active_session():
                raise SessionError("已經在統計中了")
            self._db.execute("INSERT INTO sessions (started_at, last_seen) VALUES (?, ?)", (now, now))

    def touch(self, now: float) -> None:
        with self._lock, self._db:
            self._db.execute("UPDATE sessions SET last_seen = ? WHERE ended_at IS NULL", (now,))

    def stop_session(self, now: float) -> tuple[float, int]:
        """結束目前這次，回傳（這次的秒數、這次偵測到的次數）。"""
        with self._lock, self._db:
            row = self.active_session()
            if not row:
                raise SessionError("目前沒有在統計")
            session_id, started_at = row
            self._db.execute(
                "UPDATE sessions SET ended_at = ?, last_seen = ? WHERE id = ?", (now, now, session_id)
            )
            (count,) = self._db.execute(
                "SELECT COUNT(*) FROM detections WHERE ts >= ? AND ts <= ?", (started_at, now)
            ).fetchone()
            return now - started_at, count

    def total_seconds(self, now: float) -> float:
        (total,) = self._db.execute(
            "SELECT COALESCE(SUM(COALESCE(ended_at, ?) - started_at), 0) FROM sessions", (now,)
        ).fetchone()
        return total

    # ---------- 偵測紀錄 ----------

    def add_detections(self, ts: float, user_id: str, user_name: str,
                       phrases: list[str], transcript: str) -> None:
        rows = [(ts, user_id, user_name, p, transcript) for p in phrases]
        with self._lock, self._db:
            self._db.executemany(
                "INSERT INTO detections (ts, user_id, user_name, phrase, transcript) VALUES (?, ?, ?, ?, ?)",
                rows,
            )
        self._write_log(rows)

    def log_path(self, ts: float) -> Path:
        year, week, _ = datetime.fromtimestamp(ts).isocalendar()
        return self.log_dir / f"{year}-W{week:02d}.csv"

    def _write_log(self, rows) -> None:
        self.log_dir.mkdir(parents=True, exist_ok=True)
        path = self.log_path(rows[0][0])
        is_new = not path.exists()
        # utf-8-sig 讓 Excel 正確顯示中文；附加寫入時不會重複寫 BOM
        with path.open("a", encoding="utf-8-sig", newline="") as f:
            writer = csv.writer(f)
            if is_new:
                writer.writerow(LOG_FIELDS)
            for ts, user_id, user_name, phrase, transcript in rows:
                when = datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M:%S")
                writer.writerow([when, user_id, user_name, phrase, transcript])

    # ---------- 排行榜 ----------

    def member_ranking(self, limit: int) -> list[MemberRank]:
        ranks = []
        for user_id, count in self._db.execute(
            "SELECT user_id, COUNT(*) AS c FROM detections GROUP BY user_id ORDER BY c DESC LIMIT ?",
            (limit,),
        ).fetchall():
            (name,) = self._db.execute(
                "SELECT user_name FROM detections WHERE user_id = ? ORDER BY ts DESC LIMIT 1", (user_id,)
            ).fetchone()
            top_phrase, top_count = self._db.execute(
                "SELECT phrase, COUNT(*) AS c FROM detections WHERE user_id = ? "
                "GROUP BY phrase ORDER BY c DESC LIMIT 1",
                (user_id,),
            ).fetchone()
            ranks.append(MemberRank(user_id, name, count, top_phrase, top_count))
        return ranks

    def phrase_ranking(self, limit: int) -> list[PhraseRank]:
        ranks = []
        for phrase, count in self._db.execute(
            "SELECT phrase, COUNT(*) AS c FROM detections GROUP BY phrase ORDER BY c DESC LIMIT ?",
            (limit,),
        ).fetchall():
            top_user, top_count = self._db.execute(
                "SELECT user_id, COUNT(*) AS c FROM detections WHERE phrase = ? "
                "GROUP BY user_id ORDER BY c DESC LIMIT 1",
                (phrase,),
            ).fetchone()
            ranks.append(PhraseRank(phrase, count, top_user, top_count))
        return ranks

    def user_summary(self, user_id: str) -> list[tuple[str, int]]:
        return self._db.execute(
            "SELECT phrase, COUNT(*) AS c FROM detections WHERE user_id = ? GROUP BY phrase ORDER BY c DESC",
            (user_id,),
        ).fetchall()
