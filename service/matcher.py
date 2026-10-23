"""詞庫比對。

辨識出來的文字先正規化（簡轉繁、全形轉半形、英文小寫、去掉標點），
再套用同義規則，最後由左到右、以最長優先且不重疊的方式找出詞庫裡的句子。
"""

import re
import shutil
import threading
import unicodedata
from pathlib import Path

from opencc import OpenCC

_s2t = OpenCC("s2t")
_NON_WORD = re.compile(r"[\W_]+")
# 只保留夾在兩個英數字之間的空白，例如 "your mom"；中文旁邊的空白全部拿掉
_LOOSE_SPACE = re.compile(r"(?<![a-z0-9]) | (?![a-z0-9])")
_ASCII_ALNUM = re.compile(r"[a-z0-9]")

WORDS_HEADER = """\
# 媽媽系列詞庫：一行一句。
# 「=」後面是變體（辨識可能寫出的其他寫法），用逗號分隔，會算成同一句。
# 例：你媽死了 = 你馬死了, 尼瑪死了
# 改完後在 Discord 用 /詞庫 重新載入 套用。
"""

SYNONYMS_HEADER = """\
# 同義規則：一行一條，格式為「變體 -> 標準寫法」。
# 套用在所有句子上，例如「啦 -> 了」讓「你媽死啦」算成「你媽死了」。
# 改完後在 Discord 用 /詞庫 重新載入 套用。
"""


def normalize(text: str) -> str:
    text = unicodedata.normalize("NFKC", text)
    text = _s2t.convert(text).lower()
    text = _NON_WORD.sub(" ", text).strip()
    return _LOOSE_SPACE.sub("", text)


def _is_alnum(ch: str) -> bool:
    return bool(_ASCII_ALNUM.fullmatch(ch))


class Matcher:
    def __init__(self, words_path: Path, synonyms_path: Path,
                 words_example: Path | None = None, synonyms_example: Path | None = None):
        self.words_path = words_path
        self.synonyms_path = synonyms_path
        for path, example in ((words_path, words_example), (synonyms_path, synonyms_example)):
            if not path.exists():
                path.parent.mkdir(parents=True, exist_ok=True)
                if example and example.exists():
                    shutil.copyfile(example, path)
                else:
                    path.write_text("", encoding="utf-8")
        self._lock = threading.Lock()
        self.reload()

    # ---------- 讀寫檔案 ----------

    def reload(self) -> None:
        phrases = _read_words(self.words_path)
        synonyms = _read_synonyms(self.synonyms_path)
        with self._lock:
            self.phrases = phrases
            self.synonyms = synonyms
            self._build()

    def _build(self) -> None:
        # 長的規則先套，避免「尼瑪」先被短規則改掉
        self._rules = sorted(
            ((normalize(a), normalize(b)) for a, b in self.synonyms.items()),
            key=lambda r: len(r[0]), reverse=True,
        )
        patterns: dict[str, str] = {}
        for phrase, variants in self.phrases.items():
            for form in (phrase, *variants):
                key = self._canonical(form)
                if key:
                    patterns.setdefault(key, phrase)
        self._patterns = patterns
        self._lengths = sorted({len(k) for k in patterns}, reverse=True)

    def _save_words(self) -> None:
        lines = [WORDS_HEADER]
        for phrase, variants in self.phrases.items():
            lines.append(f"{phrase} = {', '.join(variants)}" if variants else phrase)
        self.words_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    def _save_synonyms(self) -> None:
        lines = [SYNONYMS_HEADER]
        lines += [f"{a} -> {b}" for a, b in self.synonyms.items()]
        self.synonyms_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    # ---------- 指令用的增刪 ----------

    def add_phrase(self, phrase: str, variants: list[str]) -> None:
        phrase = phrase.strip()
        if not normalize(phrase):
            raise ValueError("句子不能是空的")
        variants = [v.strip() for v in variants if normalize(v)]
        with self._lock:
            merged = self.phrases.get(phrase, [])
            merged += [v for v in variants if v not in merged and v != phrase]
            self.phrases[phrase] = merged
            self._save_words()
            self._build()

    def remove_phrase(self, phrase: str) -> None:
        with self._lock:
            if phrase.strip() not in self.phrases:
                raise KeyError(f"詞庫裡沒有「{phrase}」")
            del self.phrases[phrase.strip()]
            self._save_words()
            self._build()

    def add_synonym(self, variant: str, standard: str) -> None:
        variant, standard = variant.strip(), standard.strip()
        if not normalize(variant):
            raise ValueError("變體不能是空的")
        with self._lock:
            self.synonyms[variant] = standard
            self._save_synonyms()
            self._build()

    def remove_synonym(self, variant: str) -> None:
        with self._lock:
            if variant.strip() not in self.synonyms:
                raise KeyError(f"沒有「{variant}」這條同義規則")
            del self.synonyms[variant.strip()]
            self._save_synonyms()
            self._build()

    # ---------- 比對 ----------

    def _canonical(self, text: str) -> str:
        text = normalize(text)
        for a, b in self._rules:
            text = text.replace(a, b)
        return text

    def prompt(self) -> str:
        """給 Whisper 的提示詞，讓它比較傾向寫出詞庫裡的寫法。"""
        with self._lock:
            return "，".join(self.phrases)

    def find(self, text: str) -> list[str]:
        with self._lock:
            s = self._canonical(text)
            found = []
            i = 0
            while i < len(s):
                for length in self._lengths:
                    if i + length > len(s):
                        continue
                    key = s[i:i + length]
                    if key not in self._patterns or not self._at_boundary(s, i, length):
                        continue
                    found.append(self._patterns[key])
                    i += length
                    break
                else:
                    i += 1
            return found

    @staticmethod
    def _at_boundary(s: str, i: int, length: int) -> bool:
        # 英文句子不能接在英文字中間，例如 "ur mom" 不該算到 "your mom" 裡面
        if _is_alnum(s[i]) and i > 0 and _is_alnum(s[i - 1]):
            return False
        end = i + length
        if _is_alnum(s[end - 1]) and end < len(s) and _is_alnum(s[end]):
            return False
        return True


def _content_lines(path: Path):
    for line in path.read_text(encoding="utf-8-sig").splitlines():
        line = line.strip()
        if line and not line.startswith("#"):
            yield line


def _read_words(path: Path) -> dict[str, list[str]]:
    phrases: dict[str, list[str]] = {}
    for line in _content_lines(path):
        phrase, _, rest = line.partition("=")
        phrase = phrase.strip()
        if not phrase:
            continue
        variants = [v.strip() for v in re.split(r"[,，、]", rest) if v.strip()]
        phrases.setdefault(phrase, []).extend(variants)
    return phrases


def _read_synonyms(path: Path) -> dict[str, str]:
    synonyms: dict[str, str] = {}
    for line in _content_lines(path):
        variant, sep, standard = line.partition("->")
        if sep and variant.strip():
            synonyms[variant.strip()] = standard.strip()
    return synonyms
