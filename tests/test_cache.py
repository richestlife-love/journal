import json

import pytest

from journal.cache import EntryCache, CACHE_VERSION


def test_load_missing_file_returns_empty(tmp_path):
    c = EntryCache.load(tmp_path / "missing.json")
    assert c.get("anything") is None


def test_get_returns_none_on_miss(tmp_path):
    c = EntryCache.load(tmp_path / "x.json")
    assert c.get("123") is None


def test_put_then_get_hit(tmp_path):
    c = EntryCache.load(tmp_path / "x.json")
    c.put("123", "sha256:abc")
    assert c.get("123") == "sha256:abc"


def test_save_and_reload_round_trips(tmp_path):
    path = tmp_path / "x.json"
    a = EntryCache.load(path)
    a.put("123", "sha256:abc")
    a.put("456", "sha256:def")
    a.save()

    b = EntryCache.load(path)
    assert b.get("123") == "sha256:abc"
    assert b.get("456") == "sha256:def"


def test_saved_file_has_expected_schema(tmp_path):
    path = tmp_path / "x.json"
    c = EntryCache.load(path)
    c.put("123", "sha256:abc")
    c.save()

    raw = json.loads(path.read_text())
    assert raw["version"] == CACHE_VERSION
    assert raw["entries"] == {"123": "sha256:abc"}


def test_malformed_json_falls_back_to_empty(tmp_path):
    path = tmp_path / "x.json"
    path.write_text("not json at all")
    c = EntryCache.load(path)
    assert c.get("123") is None


def test_wrong_version_falls_back_to_empty(tmp_path):
    path = tmp_path / "x.json"
    path.write_text(json.dumps({"version": 99, "entries": {"x": "sha256:y"}}))
    c = EntryCache.load(path)
    assert c.get("x") is None


def test_save_creates_parent_directories(tmp_path):
    path = tmp_path / "nested" / "dir" / "cache.json"
    c = EntryCache.load(path)
    c.put("k", "sha256:v")
    c.save()
    assert path.exists()
