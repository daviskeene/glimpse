"""Normalise user source before it is written into a sandbox.

LLM-generated snippets arrive with byte-order marks, Windows line endings, Java classes
that are not called ``Main`` and Go files that are not ``package main``. Every backend
calls :func:`prepare` so the fixes apply identically to Docker, Lambda and local runs.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from .languages import Language

_JAVA_PUBLIC_TYPE = re.compile(
    r"^[ \t]*public\s+(?:(?:final|abstract|static|sealed|non-sealed|strictfp)\s+)*"
    r"(?:class|interface|enum|record)\s+([A-Za-z_$][\w$]*)",
    re.MULTILINE,
)
_LINE_COMMENT = re.compile(r"//[^\n]*")
_BLOCK_COMMENT = re.compile(r"/\*.*?\*/", re.DOTALL)
_STRING = re.compile(r'"(?:\\.|[^"\\\n])*"')
_GO_PACKAGE_LINE = re.compile(r"^[ \t]*package[ \t]+(\w+)")


@dataclass(frozen=True, slots=True)
class PreparedSource:
    filename: str
    code: str
    stem: str


def normalize(code: str) -> str:
    """Drop a leading BOM, unify line endings and end with a newline."""
    if code.startswith("﻿"):
        code = code[1:]
    code = code.replace("\r\n", "\n").replace("\r", "\n")
    if code and not code.endswith("\n"):
        code += "\n"
    return code


def _strip_c_style(code: str) -> str:
    """Blank out strings and comments (keeping newlines) for declaration scanning."""
    code = _STRING.sub(lambda m: '"' * len(m.group(0)), code)
    code = _BLOCK_COMMENT.sub(lambda m: re.sub(r"[^\n]", " ", m.group(0)), code)
    return _LINE_COMMENT.sub("", code)


def java_public_type(code: str) -> str | None:
    """Name of the first public top-level type, e.g. ``Solution`` for ``public class Solution``."""
    match = _JAVA_PUBLIC_TYPE.search(_strip_c_style(code))
    return match.group(1) if match else None


def go_set_package_main(code: str) -> str:
    """Rewrite the package clause to ``main`` (Go requires it to be the first declaration)."""
    stripped = _strip_c_style(code)
    lines = code.split("\n")
    for index, line in enumerate(stripped.split("\n")):
        match = _GO_PACKAGE_LINE.match(line)
        if match:
            if match.group(1) != "main":
                start, end = match.span(1)
                lines[index] = lines[index][:start] + "main" + lines[index][end:]
                return "\n".join(lines)
            return code
    return code


def prepare(language: Language, code: str) -> PreparedSource:
    code = normalize(code)
    filename = language.filename
    if language.id == "java":
        name = java_public_type(code)
        if name:
            filename = f"{name}.java"
    elif language.id == "go":
        code = go_set_package_main(code)
    stem = filename.rsplit(".", 1)[0]
    return PreparedSource(filename=filename, code=code, stem=stem)
