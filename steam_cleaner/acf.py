from __future__ import annotations

import logging
import re
from pathlib import Path

LOGGER = logging.getLogger(__name__)
_TOKEN_RE = re.compile(r'"([^"\\]*(?:\\.[^"\\]*)*)"|\{|\}')


class ACFParseError(Exception):
    pass


def parse_acf(path: Path) -> dict:
    text = path.read_text(encoding="utf-8", errors="replace")
    return _parse_kv_text(text)


def extract_game_fields(parsed: dict) -> tuple[str, str, str]:
    source = parsed
    if "AppState" in parsed and isinstance(parsed["AppState"], dict):
        source = parsed["AppState"]

    appid = str(source.get("appid", "")).strip()
    name = str(source.get("name", "")).strip()
    installdir = str(source.get("installdir", "")).strip()

    if not appid:
        raise ACFParseError("appid missing")
    if not name:
        name = f"Unknown ({appid})"
    if not installdir:
        raise ACFParseError("installdir missing")

    return appid, name, installdir


def _parse_kv_text(text: str) -> dict:
    tokens: list[str | tuple[str, str]] = []
    for match in _TOKEN_RE.finditer(text):
        if match.group(1) is not None:
            tokens.append(("STRING", _unescape_acf_string(match.group(1))))
        else:
            literal = match.group(0)
            if literal == "{":
                tokens.append("LBRACE")
            elif literal == "}":
                tokens.append("RBRACE")

    root: dict = {}
    stack: list[dict] = [root]
    pending_key: str | None = None
    idx = 0

    while idx < len(tokens):
        token = tokens[idx]
        if isinstance(token, tuple) and token[0] == "STRING":
            value = token[1]
            if pending_key is None:
                pending_key = value
            else:
                stack[-1][pending_key] = value
                pending_key = None
        elif token == "LBRACE":
            if pending_key is None:
                idx += 1
                continue
            child: dict = {}
            stack[-1][pending_key] = child
            stack.append(child)
            pending_key = None
        elif token == "RBRACE":
            if len(stack) > 1:
                stack.pop()
            pending_key = None
        idx += 1

    if len(stack) != 1:
        raise ACFParseError("unbalanced braces")

    return root


def _unescape_acf_string(raw: str) -> str:
    chars: list[str] = []
    idx = 0
    mapping = {
        "\\": "\\",
        '"': '"',
        "n": "\n",
        "r": "\r",
        "t": "\t",
    }
    while idx < len(raw):
        ch = raw[idx]
        if ch == "\\" and idx + 1 < len(raw):
            nxt = raw[idx + 1]
            chars.append(mapping.get(nxt, nxt))
            idx += 2
            continue
        chars.append(ch)
        idx += 1
    return "".join(chars)
