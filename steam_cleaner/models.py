from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path


class GameState(str, Enum):
    OK = "OK"
    MISSING_INSTALL_DIR = "MissingInstallDir"
    MISSING_MANIFEST = "MissingManifest"
    ERROR = "Error"


@dataclass(slots=True)
class LibraryRoot:
    root_path: Path
    steamapps_path: Path
    common_path: Path


@dataclass(slots=True)
class MountPoint:
    path: Path
    detected_libraries: list[LibraryRoot] = field(default_factory=list)


@dataclass(slots=True)
class GameEntry:
    appid: str
    name: str
    installdir: str
    library_root: Path
    install_path: Path
    manifest_path: Path
    optional_paths_to_delete: list[Path]
    state: GameState
    error_message: str = ""

    @property
    def dedupe_key(self) -> tuple[str, str]:
        return (self.appid, str(self.library_root.resolve()))

    @property
    def display_name(self) -> str:
        if self.state == GameState.OK:
            return self.name
        if self.state == GameState.MISSING_INSTALL_DIR:
            return f"{self.name} [Missing install dir]"
        if self.state == GameState.MISSING_MANIFEST:
            return f"{self.name} [Missing manifest]"
        return f"{self.name} [Error]"

    def all_deletion_targets(self, include_optional: bool) -> list[Path]:
        targets = [self.install_path, self.manifest_path]
        if include_optional:
            targets.extend(self.optional_paths_to_delete)
        return targets
