import pytest

from service.matcher import Matcher, normalize

WORDS = """\
你媽
你媽死了 = 尼瑪死了
你媽在天上飛
你M的
your mom
ur mom
"""

SYNONYMS = """\
啦 -> 了
妳 -> 你
"""


@pytest.fixture
def matcher(tmp_path):
    (tmp_path / "words.txt").write_text(WORDS, encoding="utf-8")
    (tmp_path / "syn.txt").write_text(SYNONYMS, encoding="utf-8")
    return Matcher(tmp_path / "words.txt", tmp_path / "syn.txt")


def test_normalize():
    assert normalize("你妈死了！") == "你媽死了"
    assert normalize("Your  MOM, 哈") == "your mom哈"
    assert normalize("你ｍ的") == "你m的"


def test_longest_phrase_only(matcher):
    assert matcher.find("你媽死了") == ["你媽死了"]


def test_particles_and_prefix(matcher):
    assert matcher.find("糙你媽死啦") == ["你媽死了"]
    assert matcher.find("妳媽在天上飛啦") == ["你媽在天上飛"]


def test_variant_counts_as_phrase(matcher):
    assert matcher.find("尼玛死了") == ["你媽死了"]


def test_multiple_in_one_sentence(matcher):
    assert matcher.find("你媽啦，你媽死了") == ["你媽", "你媽死了"]


def test_mixed_chinese_english(matcher):
    assert matcher.find("你m的 很煩") == ["你M的"]


def test_english_word_boundary(matcher):
    assert matcher.find("your mom is here") == ["your mom"]
    assert matcher.find("your momentum") == []
    assert matcher.find("haha ur mom") == ["ur mom"]


def test_add_and_remove_phrase_persists(matcher, tmp_path):
    matcher.add_phrase("你媽沒了", ["你媽沒啦"])
    assert matcher.find("你媽沒了") == ["你媽沒了"]
    reloaded = Matcher(tmp_path / "words.txt", tmp_path / "syn.txt")
    assert reloaded.phrases["你媽沒了"] == ["你媽沒啦"]

    matcher.remove_phrase("你媽沒了")
    assert matcher.find("你媽沒了") == ["你媽"]


def test_add_synonym(matcher):
    matcher.add_synonym("你馬", "你媽")
    assert matcher.find("你馬在天上飛") == ["你媽在天上飛"]


def test_creates_files_from_example(tmp_path):
    example = tmp_path / "example.txt"
    example.write_text("你媽\n", encoding="utf-8")
    m = Matcher(tmp_path / "data" / "words.txt", tmp_path / "data" / "syn.txt", example, None)
    assert m.find("你媽") == ["你媽"]
