"""Owner-scoped Markdown memory with atomic writes and optimistic concurrency."""

from __future__ import annotations

import hashlib
import json
import os
import re
import tempfile
import threading
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath


class WikiConflict(ValueError):
    pass


class WikiPathError(ValueError):
    pass


@dataclass(frozen=True)
class WikiPage:
    path: str
    text: str
    sha256: str
    source: str
    updated_at: str


class WikiStore:
    def __init__(self, root: Path):
        self.root = Path(root).resolve()
        self.root.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.root.chmod(0o700)
        self._lock = threading.RLock()

    def _owner_root(self, owner_id: str) -> Path:
        if not owner_id or len(owner_id) > 200:
            raise WikiPathError("Invalid owner")
        digest = hashlib.sha256(owner_id.encode()).hexdigest()
        root = self.root / "users" / digest
        root.mkdir(parents=True, exist_ok=True, mode=0o700)
        root.chmod(0o700)
        return root

    def _path(self, owner_id: str, relative: str) -> Path:
        if not isinstance(relative, str) or len(relative) > 240 or "\\" in relative:
            raise WikiPathError("Invalid wiki path")
        path = PurePosixPath(relative)
        if path.is_absolute() or not path.parts or any(part in {"", ".", ".."} or part.startswith(".") for part in path.parts):
            raise WikiPathError("Invalid wiki path")
        if path.suffix != ".md" or not all(re.fullmatch(r"[A-Za-z0-9_\-]+(?:\.md)?", part) for part in path.parts):
            raise WikiPathError("Wiki paths must use safe Markdown names")
        root = self._owner_root(owner_id)
        target = root.joinpath(*path.parts)
        if not target.resolve().is_relative_to(root):
            raise WikiPathError("Wiki path escapes owner root")
        return target

    @staticmethod
    def _digest(text: str) -> str:
        return hashlib.sha256(text.encode("utf-8")).hexdigest()

    def read(self, owner_id: str, relative: str) -> WikiPage | None:
        target = self._path(owner_id, relative)
        if not target.is_file():
            return None
        text = target.read_text(encoding="utf-8")
        metadata = target.with_suffix(".json")
        details = json.loads(metadata.read_text(encoding="utf-8")) if metadata.is_file() else {}
        return WikiPage(relative, text, self._digest(text), details.get("source", "unknown"), details.get("updated_at", ""))

    def write(self, owner_id: str, relative: str, text: str, *, expected_sha256: str | None, source: str) -> WikiPage:
        if not isinstance(text, str) or len(text.encode("utf-8")) > 256_000:
            raise ValueError("Wiki page exceeds 256 KB")
        if not source or len(source) > 200:
            raise ValueError("Source is required and limited to 200 characters")
        with self._lock:
            target = self._path(owner_id, relative)
            existing = self.read(owner_id, relative)
            if (existing.sha256 if existing else None) != expected_sha256:
                raise WikiConflict("Wiki page changed; reload its hash before saving")
            target.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
            target.parent.chmod(0o700)
            self._atomic(target, text)
            updated = datetime.now(timezone.utc).isoformat()
            self._atomic(target.with_suffix(".json"), json.dumps({"source": source, "updated_at": updated}, ensure_ascii=False))
            return WikiPage(relative, text, self._digest(text), source, updated)

    @staticmethod
    def _atomic(path: Path, content: str) -> None:
        with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=path.parent, prefix=".wiki-", delete=False) as file:
            file.write(content)
            file.flush()
            os.fsync(file.fileno())
            temporary = Path(file.name)
        temporary.chmod(0o600)
        os.replace(temporary, path)

    def list(self, owner_id: str) -> list[str]:
        root = self._owner_root(owner_id)
        return sorted(path.relative_to(root).as_posix() for path in root.rglob("*.md") if path.is_file() and not path.is_symlink())

    def search(self, owner_id: str, query: str, *, limit: int = 8, max_characters: int = 12000) -> list[WikiPage]:
        tokens = [token.casefold() for token in re.findall(r"[\w\u3400-\u9fff]+", query) if len(token) >= 2][:12]
        if not tokens:
            return []
        ranked: list[tuple[int, WikiPage]] = []
        for relative in self.list(owner_id)[:1000]:
            page = self.read(owner_id, relative)
            if page is None:
                continue
            body = (page.path + "\n" + page.text).casefold()
            score = sum(body.count(token) for token in tokens)
            if score:
                ranked.append((score, page))
        ranked.sort(key=lambda item: (-item[0], item[1].path))
        result: list[WikiPage] = []
        remaining = max_characters
        for _, page in ranked[:limit]:
            if remaining <= 0:
                break
            clipped = page.text[:remaining]
            result.append(WikiPage(page.path, clipped, page.sha256, page.source, page.updated_at))
            remaining -= len(clipped)
        return result
