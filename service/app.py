"""本機 Python 服務：接收 Node.js 傳來的音訊與指令，負責辨識、比對、統計與排行榜。

啟動：python -m service.app
"""

import logging
import queue
import threading
import time
import wave
from dataclasses import dataclass

import uvicorn
from fastapi import FastAPI, HTTPException, Request
from pydantic import BaseModel

from . import config
from .matcher import Matcher
from .storage import SessionError, Storage

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("service")

storage = Storage(config.DB_PATH, config.LOG_DIR)
storage.recover_open_sessions()
matcher = Matcher(config.WORDS_PATH, config.SYNONYMS_PATH,
                  config.WORDS_EXAMPLE_PATH, config.SYNONYMS_EXAMPLE_PATH)

app = FastAPI()


@dataclass
class AudioJob:
    user_id: str
    user_name: str
    ts: float
    pcm: bytes


jobs: "queue.Queue[AudioJob]" = queue.Queue()
model_ready = threading.Event()


def worker() -> None:
    # 模型在背景載入，HTTP 服務可以先開起來；載入前收到的音訊會排隊
    from .transcriber import Transcriber

    try:
        transcriber = Transcriber(config.WHISPER_MODEL, config.WHISPER_DEVICE, config.WHISPER_LANGUAGE)
    except Exception:
        log.exception("語音模型載入失敗，請檢查 .env 的 WHISPER_ 設定")
        return
    model_ready.set()
    while True:
        job = jobs.get()
        try:
            text = transcriber.transcribe(job.pcm, matcher.prompt())
            if not text:
                continue
            phrases = matcher.find(text)
            log.info("%s：%s%s", job.user_name, text, f"  → {phrases}" if phrases else "")
            if phrases:
                storage.add_detections(job.ts, job.user_id, job.user_name, phrases, text)
        except Exception:
            log.exception("處理音訊失敗")


def save_recording(job: AudioJob) -> None:
    config.RECORDINGS_DIR.mkdir(parents=True, exist_ok=True)
    stamp = time.strftime("%Y%m%d-%H%M%S", time.localtime(job.ts))
    path = config.RECORDINGS_DIR / f"{stamp}_{job.user_id}.wav"
    with wave.open(str(path), "wb") as f:
        f.setnchannels(1)
        f.setsampwidth(2)
        f.setframerate(16000)
        f.writeframes(job.pcm)


# ---------- 顯示用的小工具 ----------

def fmt_duration(seconds: float) -> str:
    minutes = int(seconds // 60)
    hours, minutes = divmod(minutes, 60)
    return f"{hours} 小時 {minutes} 分" if hours else f"{minutes} 分"


def display(title: str, lines: list[str]) -> dict:
    description = "\n".join(lines)
    if len(description) > 3900:
        description = description[:3900] + "\n…（太長了，只顯示前面）"
    return {"title": title, "description": description}


def total_line() -> str:
    return f"累計收聽 {fmt_duration(storage.total_seconds(time.time()))}"


# ---------- 碼表 ----------

@app.post("/session/start")
def session_start():
    try:
        storage.start_session(time.time())
    except SessionError as e:
        raise HTTPException(400, str(e))
    return {"ok": True}


@app.post("/session/stop")
def session_stop():
    try:
        seconds, count = storage.stop_session(time.time())
    except SessionError as e:
        raise HTTPException(400, str(e))
    return display("結束統計", [
        f"這次收聽 {fmt_duration(seconds)}，偵測到 {count} 次",
        total_line(),
    ])


@app.post("/session/recover")
def session_recover():
    storage.recover_open_sessions()
    return {"ok": True}


@app.post("/heartbeat")
def heartbeat():
    storage.touch(time.time())
    return {"ok": True}


@app.get("/status")
def status():
    active = storage.active_session()
    lines = [
        f"狀態：{'收音中' if active else '未開啟'}",
        total_line(),
        f"語音模型：{'已就緒' if model_ready.is_set() else '載入中'}",
        f"等待辨識：{jobs.qsize()} 段",
    ]
    if active:
        lines.insert(1, f"這次已開啟 {fmt_duration(time.time() - active[1])}")
    return display("機器人狀態", lines)


# ---------- 音訊 ----------

@app.post("/audio")
async def audio(request: Request, user_id: str, user_name: str):
    if not storage.active_session():
        return {"queued": False}
    now = time.time()
    job = AudioJob(user_id, user_name, now, await request.body())
    storage.touch(now)
    if config.SAVE_AUDIO:
        save_recording(job)
    jobs.put(job)
    return {"queued": True}


# ---------- 排行榜 ----------

@app.get("/leaderboard/members")
def leaderboard_members(limit: int = 10):
    ranks = storage.member_ranking(limit)
    if not ranks:
        return display("媽媽系列排行榜", [total_line(), "", "目前還沒有任何紀錄"])
    lines = [total_line(), ""]
    for i, r in enumerate(ranks, 1):
        lines.append(f"{i}. <@{r.user_id}>　{r.count} 次（最愛：{r.top_phrase} × {r.top_count}）")
    return display("媽媽系列排行榜", lines)


@app.get("/leaderboard/phrases")
def leaderboard_phrases(limit: int = 10):
    ranks = storage.phrase_ranking(limit)
    if not ranks:
        return display("髒話排行榜", [total_line(), "", "目前還沒有任何紀錄"])
    lines = [total_line(), ""]
    for i, r in enumerate(ranks, 1):
        lines.append(f"{i}. {r.phrase}　{r.count} 次（最常說的人：<@{r.top_user_id}> × {r.top_count}）")
    return display("髒話排行榜", lines)


@app.get("/users/{user_id}")
def user_summary(user_id: str):
    rows = storage.user_summary(user_id)
    total = sum(c for _, c in rows)
    lines = [f"<@{user_id}> 總共 {total} 次", total_line()]
    if rows:
        lines.append("")
        lines += [f"{phrase}　× {count}" for phrase, count in rows]
    return display("個人紀錄", lines)


# ---------- 詞庫 ----------

class PhraseIn(BaseModel):
    phrase: str
    variants: list[str] = []


class SynonymIn(BaseModel):
    variant: str
    standard: str = ""


@app.get("/words")
def words():
    lines = []
    for phrase, variants in matcher.phrases.items():
        lines.append(f"• {phrase}" + (f"（變體：{'、'.join(variants)}）" if variants else ""))
    return display(f"詞庫（{len(lines)} 句）", lines or ["詞庫是空的"])


@app.post("/words")
def add_word(body: PhraseIn):
    try:
        matcher.add_phrase(body.phrase, body.variants)
    except ValueError as e:
        raise HTTPException(400, str(e))
    variants = matcher.phrases[body.phrase.strip()]
    extra = f"（變體：{'、'.join(variants)}）" if variants else ""
    return display("已加入詞庫", [f"{body.phrase.strip()}{extra}", "從現在開始計算"])


@app.post("/words/remove")
def remove_word(body: PhraseIn):
    try:
        matcher.remove_phrase(body.phrase)
    except KeyError as e:
        raise HTTPException(404, e.args[0])
    return display("已從詞庫刪除", [body.phrase.strip(), "過去的紀錄仍會保留"])


@app.post("/words/reload")
def reload_words():
    matcher.reload()
    return display("已重新載入", [f"詞庫 {len(matcher.phrases)} 句，同義規則 {len(matcher.synonyms)} 條"])


@app.get("/synonyms")
def synonyms():
    lines = [f"• {a} → {b or '（刪除）'}" for a, b in matcher.synonyms.items()]
    return display(f"同義規則（{len(lines)} 條）", lines or ["目前沒有同義規則"])


@app.post("/synonyms")
def add_synonym(body: SynonymIn):
    try:
        matcher.add_synonym(body.variant, body.standard)
    except ValueError as e:
        raise HTTPException(400, str(e))
    return display("已加入同義規則", [f"{body.variant.strip()} → {body.standard.strip() or '（刪除）'}"])


@app.post("/synonyms/remove")
def remove_synonym(body: SynonymIn):
    try:
        matcher.remove_synonym(body.variant)
    except KeyError as e:
        raise HTTPException(404, e.args[0])
    return display("已刪除同義規則", [body.variant.strip()])


if __name__ == "__main__":
    threading.Thread(target=worker, daemon=True).start()
    uvicorn.run(app, host=config.HOST, port=config.PORT, log_level="warning")
