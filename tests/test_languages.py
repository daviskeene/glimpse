from __future__ import annotations

import pytest

from glimpse import languages
from glimpse.languages import LANGUAGES, UnsupportedLanguageError


def test_ids_and_aliases_are_unique() -> None:
    names = [lang.id for lang in LANGUAGES] + [a for lang in LANGUAGES for a in lang.aliases]
    assert len(names) == len(set(names))
    assert all(name == name.lower() for name in names)


def test_every_language_is_runnable() -> None:
    for lang in LANGUAGES:
        assert lang.run, lang.id
        assert lang.filename and "/" not in lang.filename
        assert lang.version
        assert lang.extensions
        assert lang.sample.strip(), f"{lang.id} has no sample program"
        uses_out = any("{out}" in p for p in (lang.compile or ()) + lang.run)
        if uses_out:
            assert lang.artifact, f"{lang.id} uses {{out}} but has no artifact"
        if lang.compiled:
            assert any("{src}" in p for p in lang.compile or ()), lang.id
            assert any("{out}" in p or "{work}" in p for p in lang.run), lang.id
        else:
            assert any("{src}" in p for p in lang.run), lang.id
        if lang.id != "java":
            assert not any("{stem}" in p for p in (lang.compile or ()) + lang.run), lang.id


@pytest.mark.parametrize(
    ("name", "expected"),
    [
        ("python", "python"),
        ("py", "python"),
        ("PY", "python"),
        (" Python3 ", "python"),
        ("js", "javascript"),
        ("node", "javascript"),
        ("c++", "cpp"),
        ("kt", "kotlin"),
        ("golang", "go"),
        ("java", "java"),
        ("c", "c"),
        ("sh", "bash"),
        ("shell", "bash"),
        ("zsh", "bash"),
        ("ts", "typescript"),
        ("rs", "rust"),
        ("cplusplus", "cpp"),
        ("py3", "python"),
    ],
)
def test_resolve_aliases(name: str, expected: str) -> None:
    assert languages.resolve(name).id == expected


def test_resolve_unknown() -> None:
    with pytest.raises(UnsupportedLanguageError) as exc:
        languages.resolve("brainfuck")
    assert "brainfuck" in str(exc.value)
    assert "python" in str(exc.value)
    assert languages.get("brainfuck") is None


def test_from_filename() -> None:
    assert languages.from_filename("hello.go") is languages.BY_ID["go"]
    assert languages.from_filename("Main.JAVA") is languages.BY_ID["java"]
    assert languages.from_filename("x.cc") is languages.BY_ID["cpp"]
    assert languages.from_filename("README.md") is None
    assert languages.from_filename("script.sh") is languages.BY_ID["bash"]
    assert languages.from_filename("app.ts") is languages.BY_ID["typescript"]
    assert languages.from_filename("lib.rs") is languages.BY_ID["rust"]


def test_render_substitutes_placeholders() -> None:
    lang = languages.BY_ID["go"]
    assert lang.compile is not None
    argv = languages.render(lang.compile, work="/w", tmp="/t", src="/w/main.go", out="/w/main")
    assert argv == ["go", "build", "-o", "/w/main", "/w/main.go"]
    java = languages.BY_ID["java"]
    run = languages.render(
        java.run, work="/w", tmp="/t", src="/w/Solution.java", out="/w/main", stem="Solution"
    )
    assert run[-3:] == ["-cp", "/w", "Solution"]
    env = languages.render_env(lang.env, work="/w", tmp="/t")
    assert env["GOPATH"] == "/t/go"
    assert env["GOTMPDIR"] == "/t"
