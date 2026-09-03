"""The single source of truth for supported languages.

Every backend (Docker sandbox, Lambda, local subprocess) builds its commands from this
registry, so adding a language means adding one entry here and installing the
toolchain in ``sandbox/Dockerfile`` and ``lambda/Dockerfile``.

Command templates may use the placeholders ``{src}`` (path of the source file),
``{out}`` (path of the compiled artifact), ``{work}`` (the working directory),
``{tmp}`` (a writable temp directory) and ``{stem}`` (the source file name without its
extension -- the Java class name). File names and small source fixes are decided by
:mod:`glimpse.source` before a backend writes the file.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field


@dataclass(frozen=True, slots=True)
class Language:
    id: str
    name: str
    aliases: tuple[str, ...]
    filename: str
    run: tuple[str, ...]
    compile: tuple[str, ...] | None = None
    artifact: str | None = None
    version: tuple[str, ...] = ()
    env: Mapping[str, str] = field(default_factory=dict)
    compile_timeout_s: float = 20.0
    extensions: tuple[str, ...] = ()
    sample: str = ""
    """A program that reads one line from stdin and prints ``hello, <name>`` first."""

    @property
    def compiled(self) -> bool:
        return self.compile is not None


_JVM_RUN_FLAGS = (
    "-XX:-UsePerfData",
    "-XX:+UseSerialGC",
    "-XX:TieredStopAtLevel=1",
    "-Xss1m",
    "-Xmx256m",
)

LANGUAGES: tuple[Language, ...] = (
    Language(
        id="python",
        name="Python",
        aliases=("py", "python3", "py3"),
        filename="main.py",
        run=("python3", "{src}"),
        version=("python3", "--version"),
        env={"PYTHONDONTWRITEBYTECODE": "1", "PYTHONUNBUFFERED": "1", "PYTHONIOENCODING": "utf-8"},
        extensions=(".py",),
        sample="""import sys, platform

name = sys.stdin.readline().strip() or "world"
print(f"hello, {name}")
print(f"python {platform.python_version()} in a fresh sandbox")
""",
    ),
    Language(
        id="javascript",
        name="JavaScript (Node.js)",
        aliases=("js", "node", "nodejs", "mjs", "cjs"),
        filename="main.js",
        run=("node", "--max-old-space-size=256", "{src}"),
        version=("node", "--version"),
        env={"NODE_NO_WARNINGS": "1"},
        extensions=(".js", ".mjs", ".cjs"),
        sample="""const name = require("fs").readFileSync(0, "utf8").trim() || "world";
console.log(`hello, ${name}`);
console.log(`node ${process.version} in a fresh sandbox`);
""",
    ),
    Language(
        id="typescript",
        name="TypeScript (Node.js)",
        aliases=("ts", "mts"),
        filename="main.ts",
        run=("node", "--max-old-space-size=256", "{src}"),
        version=("node", "--version"),
        env={"NODE_NO_WARNINGS": "1"},
        extensions=(".ts", ".mts"),
        sample="""import { readFileSync } from "node:fs";

const name: string = readFileSync(0, "utf8").trim() || "world";
const greet = (who: string): string => `hello, ${who}`;
console.log(greet(name));
console.log(`typescript on node ${process.version} in a fresh sandbox`);
""",
    ),
    Language(
        id="bash",
        name="Bash",
        aliases=("sh", "shell", "zsh"),
        filename="main.sh",
        run=("bash", "{src}"),
        version=("bash", "--version"),
        extensions=(".sh", ".bash"),
        sample="""read -r name
echo "hello, ${name:-world}"
echo "bash ${BASH_VERSION} in a fresh sandbox"
""",
    ),
    Language(
        id="c",
        name="C",
        aliases=(),
        filename="main.c",
        compile=("gcc", "-O2", "-std=gnu17", "-Wall", "-o", "{out}", "{src}", "-lm"),
        artifact="main",
        run=("{out}",),
        version=("gcc", "--version"),
        extensions=(".c",),
        sample="""#include <stdio.h>
#include <string.h>

int main(void) {
    char name[64];
    if (!fgets(name, sizeof name, stdin) || name[0] == '\\n') strcpy(name, "world");
    name[strcspn(name, "\\n")] = 0;
    printf("hello, %s\\n", name);
    printf("gcc %d.%d in a fresh sandbox\\n", __GNUC__, __GNUC_MINOR__);
    return 0;
}
""",
    ),
    Language(
        id="cpp",
        name="C++",
        aliases=("c++", "cxx", "cc", "cplusplus"),
        filename="main.cpp",
        compile=("g++", "-O2", "-std=gnu++20", "-Wall", "-o", "{out}", "{src}"),
        artifact="main",
        run=("{out}",),
        version=("g++", "--version"),
        extensions=(".cpp", ".cc", ".cxx"),
        sample="""#include <iostream>
#include <string>

int main() {
    std::string name;
    if (!std::getline(std::cin, name) || name.empty()) name = "world";
    std::cout << "hello, " << name << "\\n";
    std::cout << "C++" << __cplusplus / 100 % 100 << " in a fresh sandbox\\n";
}
""",
    ),
    Language(
        id="rust",
        name="Rust",
        aliases=("rs",),
        filename="main.rs",
        compile=("rustc", "-O", "--edition", "2021", "-o", "{out}", "{src}"),
        artifact="main",
        run=("{out}",),
        version=("rustc", "--version"),
        compile_timeout_s=30.0,
        extensions=(".rs",),
        sample="""use std::io::{self, BufRead};

fn main() {
    let mut name = String::new();
    io::stdin().lock().read_line(&mut name).ok();
    let name = name.trim();
    let name = if name.is_empty() { "world" } else { name };
    println!("hello, {name}");
    println!("rust in a fresh sandbox");
}
""",
    ),
    Language(
        id="go",
        name="Go",
        aliases=("golang",),
        filename="main.go",
        compile=("go", "build", "-o", "{out}", "{src}"),
        artifact="main",
        run=("{out}",),
        version=("go", "version"),
        env={
            "GOPATH": "{tmp}/go",
            "GOTMPDIR": "{tmp}",
            "GOFLAGS": "-mod=mod",
            "GOPROXY": "off",
            "GOTOOLCHAIN": "local",
            "GO111MODULE": "auto",
            "CGO_ENABLED": "0",
        },
        compile_timeout_s=30.0,
        extensions=(".go",),
        sample="""package main

import (
\t"bufio"
\t"fmt"
\t"os"
\t"runtime"
\t"strings"
)

func main() {
\tname, _ := bufio.NewReader(os.Stdin).ReadString('\\n')
\tif name = strings.TrimSpace(name); name == "" {
\t\tname = "world"
\t}
\tfmt.Printf("hello, %s\\n", name)
\tfmt.Printf("%s in a fresh sandbox\\n", runtime.Version())
}
""",
    ),
    Language(
        id="java",
        name="Java",
        aliases=(),
        filename="Main.java",
        compile=("javac", "-J-XX:-UsePerfData", "-J-Xmx256m", "-d", "{work}", "{src}"),
        run=("java", *_JVM_RUN_FLAGS, "-cp", "{work}", "{stem}"),
        version=("java", "-version"),
        compile_timeout_s=30.0,
        extensions=(".java",),
        sample="""import java.util.Scanner;

public class Main {
    public static void main(String[] args) {
        Scanner in = new Scanner(System.in);
        String name = in.hasNextLine() ? in.nextLine().trim() : "";
        if (name.isEmpty()) name = "world";
        System.out.println("hello, " + name);
        System.out.println("java " + Runtime.version().feature() + " in a fresh sandbox");
    }
}
""",
    ),
    Language(
        id="kotlin",
        name="Kotlin",
        aliases=("kt", "kts"),
        filename="main.kt",
        compile=(
            "kotlinc",
            "-J-XX:-UsePerfData",
            "-J-XX:+UseSerialGC",
            "-J-XX:TieredStopAtLevel=1",
            "-J-Xmx384m",
            "-J-Xss2m",
            "-nowarn",
            "-include-runtime",
            "-d",
            "{out}",
            "{src}",
        ),
        artifact="main.jar",
        run=("java", *_JVM_RUN_FLAGS, "-jar", "{out}"),
        version=("kotlinc", "-version"),
        compile_timeout_s=60.0,
        extensions=(".kt", ".kts"),
        sample="""fun main() {
    val name = readLine()?.trim().takeUnless { it.isNullOrEmpty() } ?: "world"
    println("hello, $name")
    println("kotlin ${KotlinVersion.CURRENT} in a fresh sandbox")
}
""",
    ),
)

BY_ID: dict[str, Language] = {lang.id: lang for lang in LANGUAGES}
_LOOKUP: dict[str, Language] = {}
for _lang in LANGUAGES:
    _LOOKUP[_lang.id] = _lang
    for _alias in _lang.aliases:
        _LOOKUP[_alias] = _lang


class UnsupportedLanguageError(ValueError):
    def __init__(self, requested: str) -> None:
        self.requested = requested
        super().__init__(
            f"unsupported language {requested!r}; supported: {', '.join(BY_ID)} "
            f"(aliases accepted: {', '.join(a for lang in LANGUAGES for a in lang.aliases)})"
        )


def resolve(name: str) -> Language:
    """Return the language for an id or alias (case-insensitive) or raise."""
    key = name.strip().lower()
    try:
        return _LOOKUP[key]
    except KeyError:
        raise UnsupportedLanguageError(name) from None


def get(name: str) -> Language | None:
    return _LOOKUP.get(name.strip().lower())


def from_filename(filename: str) -> Language | None:
    """Guess a language from a file extension (``hello.go`` -> go)."""
    lower = filename.lower()
    for lang in LANGUAGES:
        if any(lower.endswith(ext) for ext in lang.extensions):
            return lang
    return None


def render(
    parts: tuple[str, ...], *, work: str, tmp: str, src: str, out: str, stem: str = "main"
) -> list[str]:
    """Substitute placeholders in a command template."""
    return [p.format(work=work, tmp=tmp, src=src, out=out, stem=stem) for p in parts]


def render_env(env: Mapping[str, str], *, work: str, tmp: str) -> dict[str, str]:
    return {k: v.format(work=work, tmp=tmp) for k, v in env.items()}
