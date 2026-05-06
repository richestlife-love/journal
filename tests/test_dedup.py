from journal.dedup import normalize_body, body_hash, dedup_count


def test_normalize_strips_html_tags():
    assert normalize_body("<p>hello <b>world</b></p>") == "hello world"


def test_normalize_collapses_whitespace():
    assert normalize_body("hello    world\n\n  again") == "hello world again"


def test_normalize_strips_leading_trailing_whitespace():
    assert normalize_body("   hello world   ") == "hello world"


def test_normalize_handles_html_entities():
    assert normalize_body("a &amp; b") == "a & b"


def test_normalize_empty_input():
    assert normalize_body("") == ""
    assert normalize_body("   ") == ""


def test_body_hash_is_deterministic():
    h1 = body_hash("the quick brown fox")
    h2 = body_hash("the quick brown fox")
    assert h1 == h2
    assert h1.startswith("sha256:")


def test_body_hash_distinguishes_distinct_text():
    assert body_hash("hello") != body_hash("world")


def test_body_hash_after_normalize_collapses_whitespace_diffs():
    a = body_hash(normalize_body("hello   world"))
    b = body_hash(normalize_body("hello world"))
    assert a == b


def test_body_hash_after_normalize_collapses_html_diffs():
    a = body_hash(normalize_body("<p>hello world</p>"))
    b = body_hash(normalize_body("<div>hello world</div>"))
    assert a == b


def test_dedup_count_collapses_identical_hashes():
    hashes = ["sha256:aaa", "sha256:aaa", "sha256:bbb", "sha256:aaa"]
    assert dedup_count(hashes) == 2


def test_dedup_count_empty():
    assert dedup_count([]) == 0
