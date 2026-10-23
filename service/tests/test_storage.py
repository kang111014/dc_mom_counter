import csv

import pytest

from service.storage import SessionError, Storage


@pytest.fixture
def storage(tmp_path):
    return Storage(tmp_path / "stats.db", tmp_path / "logs")


def test_stopwatch_only_counts_open_time(storage):
    storage.start_session(1000)
    assert storage.stop_session(1600)[0] == 600
    storage.start_session(5000)
    assert storage.total_seconds(5300) == 900


def test_cannot_start_twice(storage):
    storage.start_session(0)
    with pytest.raises(SessionError):
        storage.start_session(10)


def test_recover_uses_last_seen(storage):
    storage.start_session(1000)
    storage.touch(1300)
    storage.recover_open_sessions()
    assert storage.active_session() is None
    assert storage.total_seconds(99999) == 300


def test_rankings(storage):
    storage.start_session(0)
    storage.add_detections(10, "1", "小明", ["你媽", "你媽死了"], "你媽 你媽死了")
    storage.add_detections(20, "1", "小明", ["你媽死了"], "你媽死了")
    storage.add_detections(30, "2", "阿華", ["你媽"], "你媽")

    members = storage.member_ranking(10)
    assert [(m.name, m.count, m.top_phrase, m.top_count) for m in members] == [
        ("小明", 3, "你媽死了", 2),
        ("阿華", 1, "你媽", 1),
    ]
    phrases = storage.phrase_ranking(10)
    assert [(p.phrase, p.count) for p in phrases] == [("你媽", 2), ("你媽死了", 2)] or \
        [(p.phrase, p.count) for p in phrases] == [("你媽死了", 2), ("你媽", 2)]
    assert storage.stop_session(40) == (40, 4)


def test_weekly_log_file(storage, tmp_path):
    storage.add_detections(1792764000, "1", "小明", ["你媽"], "你媽啦")  # 2026-10-23
    storage.add_detections(1792764060, "2", "阿華", ["你媽死了"], "你媽死了")
    path = storage.log_path(1792764000)
    assert path.name == "2026-W43.csv"
    with path.open(encoding="utf-8-sig") as f:
        rows = list(csv.reader(f))
    assert rows[0] == ["時間", "使用者ID", "名稱", "髒話", "辨識原句"]
    assert [r[2:] for r in rows[1:]] == [["小明", "你媽", "你媽啦"], ["阿華", "你媽死了", "你媽死了"]]
