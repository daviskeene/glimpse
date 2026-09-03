"""Public API schema (pydantic v2)."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class ExecuteRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    language: str = Field(
        description="Language id or alias, e.g. `python`, `py`, `js`, `go`, `kt`.",
        examples=["python"],
    )
    code: str = Field(min_length=1, description="Source code to run.", examples=["print(input())"])
    stdin: str = Field(default="", description="Data made available on standard input.")
    timeout_s: float | None = Field(
        default=None,
        ge=1,
        description=(
            "Wall-clock limit for the run phase in seconds; clamped to the server's "
            "configured maximum (default 30). Server default if omitted."
        ),
    )


Phase = Literal["compile", "run"]


class ExecuteResponse(BaseModel):
    language: str = Field(description="Canonical language id.")
    phase: Phase = Field(description="Phase the process reached: `compile` or `run`.")
    exit_code: int = Field(description="Exit status of the last phase. 137 = killed (timeout/OOM).")
    timed_out: bool
    stdout: str
    stderr: str
    duration_ms: int = Field(description="Wall-clock time of the last phase in milliseconds.")
    truncated: bool = Field(
        default=False,
        description="True if stdout or stderr exceeded the output cap and was cut.",
    )
    compile_stderr: str = Field(
        default="",
        description="Compiler diagnostics (warnings) when compilation succeeded; empty otherwise.",
    )


class LanguageInfo(BaseModel):
    id: str
    name: str
    aliases: list[str]
    version: str | None = None
    compiled: bool
    filename: str = Field(default="", description="File the code is written to in the sandbox.")
    sample: str = Field(default="", description="A small program that reads a line from stdin.")


class ErrorDetail(BaseModel):
    code: str
    message: str
    details: Any | None = None


class ErrorResponse(BaseModel):
    error: ErrorDetail


class HealthResponse(BaseModel):
    status: Literal["ok", "degraded"]
    runner: str
    version: str
    details: dict[str, Any] = Field(default_factory=dict)
