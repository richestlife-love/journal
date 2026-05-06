import json
from pathlib import Path

CACHE_VERSION = 1


class EntryCache:
    def __init__(self, path: Path, entries: dict[str, str]):
        self.path = path
        self._entries = entries

    @classmethod
    def load(cls, path: Path | str) -> "EntryCache":
        path = Path(path)
        try:
            raw = json.loads(path.read_text())
            if raw.get("version") != CACHE_VERSION:
                return cls(path, {})
            entries = raw.get("entries", {})
            if not isinstance(entries, dict):
                return cls(path, {})
            return cls(path, dict(entries))
        except (FileNotFoundError, json.JSONDecodeError):
            return cls(path, {})

    def get(self, entry_id: str) -> str | None:
        return self._entries.get(entry_id)

    def put(self, entry_id: str, hash_: str) -> None:
        self._entries[entry_id] = hash_

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = {"version": CACHE_VERSION, "entries": self._entries}
        self.path.write_text(json.dumps(payload, sort_keys=True, indent=2))
