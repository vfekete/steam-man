from __future__ import annotations

import logging
from pathlib import Path

from .acf import ACFParseError, extract_game_fields, parse_acf
from .models import GameEntry, GameState, LibraryRoot, MountPoint

LOGGER = logging.getLogger(__name__)


def detect_library_roots(mount_path: Path, shallow_depth: int = 2) -> list[LibraryRoot]:
    candidates: set[Path] = set()
    mount_path = mount_path.expanduser().resolve()

    candidates.add(mount_path)
    candidates.add(mount_path / "SteamLibrary")

    for parent in _walk_dirs(mount_path, shallow_depth):
        candidates.add(parent)

    libraries: list[LibraryRoot] = []
    seen: set[str] = set()

    for candidate in candidates:
        steamapps = candidate / "steamapps"
        if not steamapps.is_dir():
            continue
        root = candidate.resolve()
        key = str(root)
        if key in seen:
            continue
        seen.add(key)
        libraries.append(
            LibraryRoot(
                root_path=root,
                steamapps_path=steamapps,
                common_path=steamapps / "common",
            )
        )

    libraries.sort(key=lambda lib: str(lib.root_path))
    return libraries


def scan_mount_point(mount_path: Path) -> tuple[MountPoint, list[GameEntry]]:
    libraries = detect_library_roots(mount_path)
    mount = MountPoint(path=mount_path.expanduser().resolve(), detected_libraries=libraries)
    games: list[GameEntry] = []

    for library in libraries:
        games.extend(scan_library_games(library))

    LOGGER.info("Scanned mount '%s': %d libraries, %d games", mount.path, len(libraries), len(games))
    return mount, games


def scan_library_games(library: LibraryRoot) -> list[GameEntry]:
    games: list[GameEntry] = []
    manifests = sorted(library.steamapps_path.glob("appmanifest_*.acf"))

    for manifest_path in manifests:
        try:
            parsed = parse_acf(manifest_path)
            appid, name, installdir = extract_game_fields(parsed)
            name = _utf8_safe_text(name)
            install_path = library.common_path / installdir

            state = GameState.OK
            if not manifest_path.exists():
                state = GameState.MISSING_MANIFEST
            elif not install_path.exists():
                state = GameState.MISSING_INSTALL_DIR

            optional = [
                library.steamapps_path / "compatdata" / appid,
                library.steamapps_path / "shadercache" / appid,
                library.steamapps_path / "downloading" / appid,
                library.steamapps_path / "temp" / appid,
            ]

            games.append(
                GameEntry(
                    appid=appid,
                    name=name,
                    installdir=installdir,
                    library_root=library.root_path,
                    install_path=install_path,
                    manifest_path=manifest_path,
                    optional_paths_to_delete=optional,
                    state=state,
                )
            )
        except (OSError, ACFParseError, UnicodeError) as exc:
            LOGGER.warning("Failed to parse manifest '%s': %s", manifest_path, exc)
            games.append(
                GameEntry(
                    appid=_manifest_name_to_appid(manifest_path),
                    name=_utf8_safe_text(manifest_path.name),
                    installdir="",
                    library_root=library.root_path,
                    install_path=library.common_path,
                    manifest_path=manifest_path,
                    optional_paths_to_delete=[],
                    state=GameState.ERROR,
                    error_message=str(exc),
                )
            )

    return games


def _manifest_name_to_appid(path: Path) -> str:
    stem = path.stem
    prefix = "appmanifest_"
    if stem.startswith(prefix):
        return stem[len(prefix) :]
    return "unknown"


def _walk_dirs(base: Path, depth: int):
    if depth < 1:
        return
    try:
        for entry in base.iterdir():
            if not entry.is_dir():
                continue
            yield entry
            if depth > 1:
                yield from _walk_dirs(entry, depth - 1)
    except (OSError, PermissionError):
        return


def _utf8_safe_text(value: str) -> str:
    return str(value).encode("utf-8", errors="replace").decode("utf-8", errors="replace")
