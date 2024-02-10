from pathlib import Path
from typing import Literal

supported_languages = ["java", "cpp", "py", "c", "js", "go"]


def command_map(job_id: str, language: Literal["java", "cpp", "py", "c", "js", "go"]):
    """
    Takes in a job_id (a UUID assigned to a submission run task) and a programming language,
    returns the necessary commands that we need to execute the code provided.

    :param job_id: A string representing the UUID of the job task we want to run.
    :param language: Valid language that we can execute. Current list of supported options is
    declared in this file.
    """
    cwd = Path.cwd()
    languages = {
        "java": {
            "executeCodeCommand": "java",
            "executionArgs": [str(cwd / "submissions" / f"{job_id}.java")],
            "compilerInfoCommand": "java --version",
        },
        "cpp": {
            "compileCodeCommand": "g++",
            "compilationArgs": [
                str(cwd / "submissions" / f"{job_id}.cpp"),
                "-o",
                str(cwd / "outputs" / f"{job_id}.out"),
            ],
            "executeCodeCommand": str(cwd / "outputs" / f"{job_id}.out"),
            "outputExt": "out",
            "compilerInfoCommand": "g++ --version",
        },
        "py": {
            "executeCodeCommand": "python3",
            "executionArgs": [str(cwd / "submissions" / f"{job_id}.py")],
            "compilerInfoCommand": "python3 --version",
        },
        "c": {
            "compileCodeCommand": "gcc",
            "compilationArgs": [
                str(cwd / "submissions" / f"{job_id}.c"),
                "-o",
                str(cwd / "outputs" / f"{job_id}.out"),
            ],
            "executeCodeCommand": str(cwd / "outputs" / f"{job_id}.out"),
            "outputExt": "out",
            "compilerInfoCommand": "gcc --version",
        },
        "js": {
            "executeCodeCommand": "node",
            "executionArgs": [str(cwd / "submissions" / f"{job_id}.js")],
            "compilerInfoCommand": "node --version",
        },
        "go": {
            "executeCodeCommand": "go",
            "executionArgs": ["run", str(cwd / "submissions" / f"{job_id}.go")],
            "compilerInfoCommand": "go version",
        },
    }
    return languages.get(language, {})
