import type { Extension } from "@codemirror/state";
import { StreamLanguage } from "@codemirror/language";
import { python } from "@codemirror/lang-python";
import { javascript } from "@codemirror/lang-javascript";
import { java } from "@codemirror/lang-java";
import { cpp } from "@codemirror/lang-cpp";
import { go } from "@codemirror/lang-go";
import { rust } from "@codemirror/lang-rust";
import { kotlin } from "@codemirror/legacy-modes/mode/clike";
import { shell } from "@codemirror/legacy-modes/mode/shell";

export interface LanguageDef {
  id: string;
  label: string;
  /** The file name the sandbox writes the code to. */
  file: string;
  compiled: boolean;
  editor: () => Extension;
  samples: { hello: string; timeout: string };
}

export const DEFAULT_STDIN = "glimpse";

export const LANGUAGES: LanguageDef[] = [
  {
    id: "python",
    label: "Python",
    file: "main.py",
    compiled: false,
    editor: () => python(),
    samples: {
      hello: `import sys, platform

name = sys.stdin.readline().strip() or "world"
print(f"hello, {name}")
print(f"python {platform.python_version()} in a fresh sandbox")
`,
      timeout: `# Runs until the sandbox kills it at the timeout.
while True:
    pass
`,
    },
  },
  {
    id: "javascript",
    label: "JavaScript",
    file: "main.js",
    compiled: false,
    editor: () => javascript(),
    samples: {
      hello: `const name = require("fs").readFileSync(0, "utf8").trim() || "world";
console.log(\`hello, \${name}\`);
console.log(\`node \${process.version} in a fresh sandbox\`);
`,
      timeout: `// Runs until the sandbox kills it at the timeout.
for (;;) {}
`,
    },
  },
  {
    id: "typescript",
    label: "TypeScript",
    file: "main.ts",
    compiled: false,
    editor: () => javascript({ typescript: true }),
    samples: {
      hello: `import { readFileSync } from "node:fs";

const name: string = readFileSync(0, "utf8").trim() || "world";
const greet = (who: string): string => \`hello, \${who}\`;
console.log(greet(name));
console.log(\`typescript on node \${process.version} in a fresh sandbox\`);
`,
      timeout: `// Runs until the sandbox kills it at the timeout.
for (;;) {}
`,
    },
  },
  {
    id: "bash",
    label: "Bash",
    file: "main.sh",
    compiled: false,
    editor: () => StreamLanguage.define(shell),
    samples: {
      hello: `read -r name
echo "hello, \${name:-world}"
echo "bash \${BASH_VERSION} in a fresh sandbox"
`,
      timeout: `# Runs until the sandbox kills it at the timeout.
while true; do :; done
`,
    },
  },
  {
    id: "c",
    label: "C",
    file: "main.c",
    compiled: true,
    editor: () => cpp(),
    samples: {
      hello: `#include <stdio.h>
#include <string.h>

int main(void) {
    char name[64];
    if (!fgets(name, sizeof name, stdin) || name[0] == '\\n') strcpy(name, "world");
    name[strcspn(name, "\\n")] = 0;
    printf("hello, %s\\n", name);
    printf("gcc %d.%d in a fresh sandbox\\n", __GNUC__, __GNUC_MINOR__);
    return 0;
}
`,
      timeout: `/* Runs until the sandbox kills it at the timeout. */
int main(void) { for (;;) {} }
`,
    },
  },
  {
    id: "cpp",
    label: "C++",
    file: "main.cpp",
    compiled: true,
    editor: () => cpp(),
    samples: {
      hello: `#include <iostream>
#include <numeric>
#include <string>
#include <vector>

int main() {
    std::string name;
    if (!std::getline(std::cin, name) || name.empty()) name = "world";
    std::vector<int> v{1, 2, 3, 4, 5};
    std::cout << "hello, " << name << "\\n";
    std::cout << "sum of 1..5 is " << std::accumulate(v.begin(), v.end(), 0)
              << " (C++" << __cplusplus / 100 % 100 << ")\\n";
}
`,
      timeout: `// Runs until the sandbox kills it at the timeout.
int main() { for (;;) {} }
`,
    },
  },
  {
    id: "rust",
    label: "Rust",
    file: "main.rs",
    compiled: true,
    editor: () => rust(),
    samples: {
      hello: `use std::io::{self, BufRead};

fn main() {
    let mut name = String::new();
    io::stdin().lock().read_line(&mut name).ok();
    let name = name.trim();
    let name = if name.is_empty() { "world" } else { name };
    println!("hello, {name}");
    println!("rust in a fresh sandbox");
}
`,
      timeout: `// Runs until the sandbox kills it at the timeout.
fn main() {
    loop {}
}
`,
    },
  },
  {
    id: "java",
    label: "Java",
    file: "Main.java",
    compiled: true,
    editor: () => java(),
    samples: {
      hello: `import java.util.Scanner;

public class Main {
    public static void main(String[] args) {
        Scanner in = new Scanner(System.in);
        String name = in.hasNextLine() ? in.nextLine().trim() : "";
        if (name.isEmpty()) name = "world";
        System.out.println("hello, " + name);
        System.out.println("java " + Runtime.version().feature() + " in a fresh sandbox");
    }
}
`,
      timeout: `// Runs until the sandbox kills it at the timeout.
public class Main {
    public static void main(String[] args) {
        while (true) {}
    }
}
`,
    },
  },
  {
    id: "go",
    label: "Go",
    file: "main.go",
    compiled: true,
    editor: () => go(),
    samples: {
      hello: `package main

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
`,
      timeout: `package main

// Runs until the sandbox kills it at the timeout.
func main() {
\tfor {
\t}
}
`,
    },
  },
  {
    id: "kotlin",
    label: "Kotlin",
    file: "main.kt",
    compiled: true,
    editor: () => StreamLanguage.define(kotlin),
    samples: {
      hello: `fun main() {
    val name = readLine()?.trim().takeUnless { it.isNullOrEmpty() } ?: "world"
    println("hello, $name")
    println("kotlin \${KotlinVersion.CURRENT} in a fresh sandbox")
}
`,
      timeout: `// Runs until the sandbox kills it at the timeout.
fun main() {
    while (true) {}
}
`,
    },
  },
];

export const byId = (id: string): LanguageDef => LANGUAGES.find((l) => l.id === id) ?? LANGUAGES[0];
