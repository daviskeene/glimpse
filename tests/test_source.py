from __future__ import annotations

import pytest

from glimpse import source
from glimpse.languages import BY_ID


def test_normalize_bom_crlf_and_trailing_newline() -> None:
    assert source.normalize("﻿print(1)\r\nprint(2)\rprint(3)") == "print(1)\nprint(2)\nprint(3)\n"
    assert source.normalize("") == ""
    assert source.normalize("x\n") == "x\n"


@pytest.mark.parametrize(
    ("code", "expected"),
    [
        ("public class Solution { }", "Solution"),
        ("  public final class Solution{}", "Solution"),
        ("public abstract class Base {}", "Base"),
        ("public record Point(int x, int y) {}", "Point"),
        ("public enum Color { RED }", "Color"),
        ("public interface Shape {}", "Shape"),
        ("import java.util.*;\n\npublic class Calc {\n}", "Calc"),
        ("// public class Nope\n/* public class Nah */\npublic class Yes {}", "Yes"),
        ('String s = "public class Fake";\npublic class Real {}', "Real"),
        ("class Helper {}\npublic class $Weird_1 {}", "$Weird_1"),
        ("class Main { public static void main(String[] a) {} }", None),
        ("public static void main(String[] args) {}", None),
        ("", None),
    ],
)
def test_java_public_type(code: str, expected: str | None) -> None:
    assert source.java_public_type(code) == expected


@pytest.mark.parametrize(
    ("code", "expected"),
    [
        ("@Deprecated public class Marked {}", "Marked"),
        ('@SuppressWarnings("unchecked") public class Annotated {}', "Annotated"),
        ('String s = """\npublic class Fake {}\n""";\npublic class Real {}', "Real"),
    ],
)
def test_java_public_type_annotations_and_text_blocks(code: str, expected: str) -> None:
    assert source.java_public_type(code) == expected


@pytest.mark.parametrize(
    ("code", "expected"),
    [
        ("package com.example.app;\npublic class X {}\n", "\npublic class X {}\n"),
        ("  package a.b ;  // note\nclass Y {}\n", "  // note\nclass Y {}\n"),
        ("// package fake;\npublic class Z {}\n", "// package fake;\npublic class Z {}\n"),
        ("public class NoPkg {}\n", "public class NoPkg {}\n"),
    ],
)
def test_java_strip_package(code: str, expected: str) -> None:
    assert source.java_strip_package(code) == expected


def test_prepare_java_strips_package_and_names_file() -> None:
    prepared = source.prepare(BY_ID["java"], "package com.foo;\npublic class Solution { }\n")
    assert prepared.filename == "Solution.java"
    assert "package" not in prepared.code


def test_prepare_java_picks_filename_and_stem() -> None:
    prepared = source.prepare(BY_ID["java"], "public class Solution {}")
    assert prepared.filename == "Solution.java"
    assert prepared.stem == "Solution"
    fallback = source.prepare(BY_ID["java"], "class Foo {}")
    assert fallback.filename == "Main.java"
    assert fallback.stem == "Main"


@pytest.mark.parametrize(
    ("code", "expected"),
    [
        ("package foo\n\nfunc main() {}\n", "package main\n\nfunc main() {}\n"),
        ("package main\nfunc main() {}\n", "package main\nfunc main() {}\n"),
        (
            "// package comment\npackage utils // trailing\nfunc main() {}\n",
            "// package comment\npackage main // trailing\nfunc main() {}\n",
        ),
        (
            "/* header\npackage nope */\npackage tools\n",
            "/* header\npackage nope */\npackage main\n",
        ),
        ("func main() {}\n", "func main() {}\n"),
    ],
)
def test_go_set_package_main(code: str, expected: str) -> None:
    assert source.go_set_package_main(code) == expected


def test_prepare_go_rewrites_package() -> None:
    prepared = source.prepare(BY_ID["go"], "package hello\r\nfunc main() {}")
    assert prepared.code == "package main\nfunc main() {}\n"
    assert prepared.filename == "main.go"


def test_prepare_other_languages_untouched() -> None:
    prepared = source.prepare(BY_ID["python"], "﻿print('hi')\r\n")
    assert prepared == source.PreparedSource("main.py", "print('hi')\n", "main")
