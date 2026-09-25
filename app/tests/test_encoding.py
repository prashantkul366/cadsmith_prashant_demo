"""Guard against locale-dependent text I/O.

On Linux and macOS `open()` and `Path.read_text()` default to UTF-8, so a
missing `encoding=` is invisible. On Windows they default to the ANSI code
page (cp1252 for most installs), and any non-ASCII byte raises
UnicodeDecodeError. That is not hypothetical here: index.html contains box
drawing characters, generated CadQuery routinely contains degree signs, and
Judge feedback is free-form model text.

These tests read the source, not the runtime, so they fail on the machine
that introduces the bug rather than on the Windows machine that hits it.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SCANNED = ("app", "autofab", "scripts")
SKIP_DIRS = {".git", ".venv", "venv", "node_modules", "__pycache__", "build", "dist"}

TEXT_METHODS = {"read_text", "write_text"}


def _python_files() -> list[Path]:
    files = [PROJECT_ROOT / "run.py"]
    for name in SCANNED:
        root = PROJECT_ROOT / name
        if root.exists():
            files.extend(root.rglob("*.py"))
    return [
        f for f in sorted(set(files))
        if f.exists() and not SKIP_DIRS.intersection(f.relative_to(PROJECT_ROOT).parts)
    ]


def _mode_of(call: ast.Call, positional_index: int) -> str:
    """Best-effort read of an open() mode argument; assume text when unknown."""
    for keyword in call.keywords:
        if keyword.arg == "mode" and isinstance(keyword.value, ast.Constant):
            return str(keyword.value.value)
    if len(call.args) > positional_index:
        arg = call.args[positional_index]
        if isinstance(arg, ast.Constant):
            return str(arg.value)
    return "r"


def _offenders(path: Path) -> list[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    rel = path.relative_to(PROJECT_ROOT)
    found: list[str] = []

    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        has_encoding = any(k.arg == "encoding" for k in node.keywords)
        func = node.func

        if isinstance(func, ast.Attribute) and func.attr in TEXT_METHODS:
            if not has_encoding:
                found.append(f"{rel}:{node.lineno}: .{func.attr}() without encoding=")
        elif isinstance(func, ast.Attribute) and func.attr == "open":
            # Path.open(mode, ...) -- mode is the first positional argument.
            if "b" not in _mode_of(node, 0) and not has_encoding:
                found.append(f"{rel}:{node.lineno}: Path.open() text mode without encoding=")
        elif isinstance(func, ast.Name) and func.id == "open":
            # open(file, mode, ...) -- mode is the second positional argument.
            if "b" not in _mode_of(node, 1) and not has_encoding:
                found.append(f"{rel}:{node.lineno}: open() text mode without encoding=")

    return found


def test_text_file_io_declares_an_encoding() -> None:
    offenders = [line for path in _python_files() for line in _offenders(path)]
    assert not offenders, (
        "Text-mode file I/O without an explicit encoding fails on Windows:\n  "
        + "\n  ".join(offenders)
    )


def test_subprocess_pipes_declare_an_encoding() -> None:
    """`text=True` alone decodes child output with the locale codec."""
    offenders: list[str] = []

    for path in _python_files():
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        rel = path.relative_to(PROJECT_ROOT)
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            func = node.func
            if not (isinstance(func, ast.Attribute)
                    and func.attr in {"run", "Popen", "check_output"}
                    and isinstance(func.value, ast.Name)
                    and func.value.id == "subprocess"):
                continue
            kwargs = {k.arg: k.value for k in node.keywords}
            wants_text = any(
                isinstance(kwargs.get(name), ast.Constant) and kwargs[name].value
                for name in ("text", "universal_newlines")
            )
            if wants_text and "encoding" not in kwargs:
                offenders.append(
                    f"{rel}:{node.lineno}: subprocess.{func.attr}(text=True) without encoding="
                )

    assert not offenders, (
        "Decoding a subprocess pipe with the locale codec fails on Windows:\n  "
        + "\n  ".join(offenders)
    )


@pytest.mark.parametrize("name", ["index.html", "app.js", "style.css", "viewer.js"])
def test_frontend_assets_are_utf8(name: str) -> None:
    """The server serves these by reading them as text; they must be valid UTF-8."""
    asset = PROJECT_ROOT / "app" / "web" / name
    if not asset.exists():
        pytest.skip(f"{name} is not present")
    asset.read_bytes().decode("utf-8")  # raises UnicodeDecodeError on failure


def test_index_route_reads_a_non_ascii_page(tmp_path, monkeypatch) -> None:
    """Regression: GET / used to 500 on Windows because index.html has box drawing."""
    from fastapi.testclient import TestClient

    from app.server import app as app_module

    page = tmp_path / "index.html"
    page.write_text("<h1>══ CADSmith ° → █</h1>", encoding="utf-8")
    monkeypatch.setattr(app_module, "WEB_DIR", tmp_path)

    with TestClient(app_module.app) as client:
        response = client.get("/")

    assert response.status_code == 200
    assert "CADSmith" in response.text
