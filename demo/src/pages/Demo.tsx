import React, { useState, useCallback } from "react";
import { Code2, Play, Terminal, RefreshCcw } from "lucide-react";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Button } from "@/components/ui/button";
import { Alert, AlertDescription } from "@/components/ui/alert";

// Note: You'll need to install these packages:
// npm install @uiw/react-codemirror @codemirror/lang-python @codemirror/lang-javascript @codemirror/lang-java @codemirror/lang-cpp
import CodeMirror from "@uiw/react-codemirror";
import { python } from "@codemirror/lang-python";
import { javascript } from "@codemirror/lang-javascript";
import { java } from "@codemirror/lang-java";
import { cpp } from "@codemirror/lang-cpp";
import { EditorView } from "@codemirror/view";

const CodePlayground = () => {
  const [code, setCode] = useState('print("Hello, world!")');
  const [input, setInput] = useState("");
  const [output, setOutput] = useState("");
  const [error, setError] = useState("");
  const [language, setLanguage] = useState("py");
  const [isLoading, setIsLoading] = useState(false);

  const languages = [
    { value: "py", label: "Python", hello: 'print("Hello, world!")' },
    {
      value: "js",
      label: "JavaScript",
      hello: 'console.log("Hello, world!");',
    },
    // { value: 'java', label: 'Java', hello: 'public class Main {\n    public static void main(String[] args) {\n        System.out.println("Hello, world!");\n    }\n}' },
    // { value: 'cpp', label: 'C++', hello: '#include <iostream>\n\nint main() {\n    std::cout << "Hello, world!" << std::endl;\n    return 0;\n}' },
    // { value: 'c', label: 'C', hello: '#include <stdio.h>\n\nint main() {\n    printf("Hello, world!\\n");\n    return 0;\n}' },
    // { value: 'go', label: 'Go', hello: 'package main\n\nimport "fmt"\n\nfunc main() {\n    fmt.Println("Hello, world!")\n}' }
  ];

  const getLanguageExtension = useCallback((lang: string) => {
    switch (lang) {
      case "py":
        return python();
      case "js":
        return javascript();
      case "java":
        return java();
      case "cpp":
      case "c":
        return cpp();
      default:
        return python();
    }
  }, []);

  const runCode = async () => {
    setIsLoading(true);
    setError("");
    setOutput("");

    try {
      const response = await fetch(
        "https://glimpse-7eir.onrender.com/run-code-lambda",
        {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
          },
          body: JSON.stringify({
            language,
            code,
            input,
          }),
        },
      );

      const { body } = await response.json();
      const data = JSON.parse(body);
      setOutput(data.output);
      setError(data.error);
    } catch (err) {
      setError("Failed to execute code. Please try again.");
    } finally {
      setIsLoading(false);
    }
  };

  const loadHelloWorld = () => {
    const selectedLang = languages.find((lang) => lang.value === language);
    if (selectedLang) {
      setCode(selectedLang.hello);
    }
  };

  const handleLanguageChange = (newLanguage: string) => {
    setLanguage(newLanguage);
    const selectedLang = languages.find((lang) => lang.value === newLanguage);
    if (selectedLang) {
      setCode(selectedLang.hello);
    }
  };

  return (
    <div className="min-h-screen bg-gray-50 p-8">
      <div className="max-w-8xl mx-auto space-y-8">
        {/* Hero Section */}
        <div className="text-center space-y-4">
          <h1 className="text-4xl font-bold text-gray-900">
            Glimpse: Code Execution API
          </h1>
          <p className="text-xl text-gray-600">
            Run code snippets directly from your browser.
          </p>
        </div>

        {/* Main Playground */}
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          {/* Code Input Section */}
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center space-x-2">
                <Code2 className="w-5 h-5" />
                <span>Code Editor</span>
              </CardTitle>
              <CardDescription>
                Select your language and begin writing code
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="flex items-center space-x-4">
                <Select value={language} onValueChange={handleLanguageChange}>
                  <SelectTrigger className="w-40">
                    <SelectValue placeholder="Select language" />
                  </SelectTrigger>
                  <SelectContent>
                    {languages.map((lang) => (
                      <SelectItem key={lang.value} value={lang.value}>
                        {lang.label}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
                <Button
                  onClick={runCode}
                  disabled={isLoading}
                  className="flex items-center space-x-2"
                >
                  <Play className="w-4 h-4" />
                  <span>{isLoading ? "Running..." : "Run Code"}</span>
                </Button>
              </div>

              <div className="border rounded-lg overflow-hidden text-left">
                <CodeMirror
                  value={code}
                  height="400px"
                  theme="dark"
                  extensions={[
                    getLanguageExtension(language),
                    EditorView.lineWrapping,
                    EditorView.theme({
                      "&": { height: "400px" },
                      ".cm-scroller": { overflow: "auto" },
                      ".cm-gutters": {
                        backgroundColor: "#1f2937",
                        color: "#6b7280",
                        border: "none",
                      },
                      ".cm-activeLineGutter": { backgroundColor: "#374151" },
                      ".cm-activeLine": { backgroundColor: "#374151" },
                      ".cm-line": {
                        padding: "0",
                        marginLeft: "0",
                      },
                      ".cm-content": {
                        padding: "0",
                        marginLeft: "0",
                      },
                    }),
                  ]}
                  onChange={(value) => setCode(value)}
                  basicSetup={{
                    lineNumbers: true,
                    highlightActiveLineGutter: true,
                    highlightActiveLine: true,
                    indentOnInput: true,
                    bracketMatching: true,
                    closeBrackets: true,
                    autocompletion: true,
                    rectangularSelection: true,
                    crosshairCursor: true,
                    highlightSelectionMatches: true,
                    foldGutter: true,
                    tabSize: 4,
                  }}
                />
              </div>

              <textarea
                value={input}
                onChange={(e) => setInput(e.target.value)}
                className="w-full h-20 p-4 font-mono text-sm border rounded-lg text-gray-100 bg-gray-900"
                placeholder="Program input (optional)"
              />
            </CardContent>
          </Card>

          {/* Output Section */}
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center space-x-2">
                <Terminal className="w-5 h-5" />
                <span>Output</span>
              </CardTitle>
              <CardDescription>
                Program output and execution results
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              {error && (
                <Alert variant="destructive">
                  <AlertDescription className="font-mono text-sm whitespace-pre-wrap">
                    {error}
                  </AlertDescription>
                </Alert>
              )}

              <div className="bg-gray-900 rounded-lg p-4 min-h-[24rem]">
                <pre className="font-mono text-sm text-gray-100 whitespace-pre-wrap text-left">
                  {output || "Program output will appear here..."}
                </pre>
              </div>
            </CardContent>
          </Card>
        </div>
      </div>
    </div>
  );
};

export default CodePlayground;
