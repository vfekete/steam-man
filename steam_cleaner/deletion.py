from __future__ import annotations

import logging
import shutil
from dataclasses import dataclass
from pathlib import Path

from .models import GameEntry

LOGGER = logging.getLogger(__name__)


@dataclass(slots=True)
class DeleteFailure:
    path: Path
    error: str


@dataclass(slots=True)
class DeleteResult:
    game: GameEntry
    deleted_paths: list[Path]
    failures: list[DeleteFailure]

    @property
    def success(self) -> bool:
        return not self.failures


def delete_game(
    game: GameEntry,
    include_optional: bool,
    dry_run: bool,
    progress_cb=None,
) -> DeleteResult:
    deleted: list[Path] = []
    failures: list[DeleteFailure] = []
    targets = game.all_deletion_targets(include_optional=include_optional)

    for idx, target in enumerate(targets, start=1):
        if progress_cb:
            progress_cb(idx, len(targets), game, target)

        if not target.exists():
            continue

        LOGGER.info("Delete target for %s (%s): %s", game.name, game.appid, target)

        if dry_run:
            deleted.append(target)
            continue

        try:
            if target.is_dir() and not target.is_symlink():
                shutil.rmtree(target)
            else:
                target.unlink()
            deleted.append(target)
        except Exception as exc:  # best-effort delete with detailed failure reporting
            LOGGER.exception("Failed deleting %s: %s", target, exc)
            failures.append(DeleteFailure(path=target, error=str(exc)))

    return DeleteResult(game=game, deleted_paths=deleted, failures=failures)
