"""Whisper 語音辨識（faster-whisper）。"""

import glob
import logging
import os
import site
import sys

import numpy as np

log = logging.getLogger(__name__)


def _add_cuda_dll_dirs() -> None:
    """Windows 上讓 ctranslate2 找得到 pip 安裝的 cuBLAS / cuDNN DLL。"""
    if sys.platform != "win32":
        return
    bases = site.getsitepackages() + [site.getusersitepackages()]
    for base in bases:
        for path in glob.glob(os.path.join(base, "nvidia", "*", "bin")):
            os.add_dll_directory(path)
            os.environ["PATH"] = path + os.pathsep + os.environ["PATH"]


class Transcriber:
    def __init__(self, model: str, device: str, language: str | None):
        _add_cuda_dll_dirs()
        from faster_whisper import WhisperModel

        self.language = language
        try:
            self.model = WhisperModel(model, device=device,
                                      compute_type="float16" if device == "cuda" else "int8")
            # 先跑一次，GPU 函式庫有缺的話會在這裡就發現
            self._run(np.zeros(16000, dtype=np.float32), None)
            log.info("Whisper 模型 %s 已載入（%s）", model, device)
        except Exception as e:
            if device == "cpu":
                raise
            log.warning("GPU 載入失敗，改用 CPU（會比較慢）：%s", e)
            self.model = WhisperModel(model, device="cpu", compute_type="int8")

    def transcribe(self, pcm16: bytes, prompt: str | None) -> str:
        """pcm16：16kHz 單聲道 16-bit 的原始音訊。"""
        audio = np.frombuffer(pcm16, dtype=np.int16).astype(np.float32) / 32768.0
        return self._run(audio, prompt)

    def _run(self, audio: np.ndarray, prompt: str | None) -> str:
        segments, _ = self.model.transcribe(
            audio,
            language=self.language,
            initial_prompt=prompt or None,
            vad_filter=True,
            condition_on_previous_text=False,
            beam_size=5,
        )
        # no_speech_prob 高的段落多半是雜音被「腦補」成句子，直接丟掉
        return "".join(s.text for s in segments if s.no_speech_prob < 0.6).strip()
