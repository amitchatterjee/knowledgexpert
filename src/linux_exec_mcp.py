import os
import json
import logging
import shlex
import subprocess
from typing import List

from fastmcp import FastMCP
from pydantic import BaseModel, Field
from starlette.requests import Request
from starlette.responses import PlainTextResponse

from knowledgexpert.util import resolve_env_vars

class ExecRequest(BaseModel):
    command: str = Field(..., description="Command to execute (e.g. 'ls -la')")
    timeout: int | None = Field(60, description="Timeout in seconds for the command")

class ExecResponse(BaseModel):
    stdout: str = Field(description="Standard output from the command")
    stderr: str = Field(description="Standard error from the command")
    returncode: int = Field(description="Command exit code")
    executed_command: str = Field(description="The exact command that was executed")
    working_dir: str = Field(description="Working directory where the command ran")


logger = logging.getLogger()

# Load configuration (working_dir, allowed_commands)
config_path = os.path.join(
    os.path.expanduser("~"), ".knowledgexpert", "conf", "linux_exec", "config-mcp.json"
)
if os.path.exists(config_path):
    with open(config_path, "r") as f:
        try:
            _cfg = resolve_env_vars(json.load(f))
        except Exception:
            _cfg = {}
else:
    _cfg = {}

WORKING_DIR: str = _cfg.get("working_dir", os.getcwd())
ALLOWED_COMMANDS: List[str] = _cfg.get("allowed_commands", [])

mcp = FastMCP(name="Linux Exec MCP Server")

@mcp.tool(
    name="ShellCommandExecutor",
    description=(
        "Execute allowed Linux commands. Commands are validated against the configured "
        "allowed_commands list and run from the configured working directory. "
        f"Allowed commands: {', '.join(ALLOWED_COMMANDS) if ALLOWED_COMMANDS else 'ANY (no allowlist set)'}"
    ),
)
def exec_command(request: ExecRequest) -> ExecResponse:
    logger.debug("Received exec request: %s", request.model_dump_json())

    parts = shlex.split(request.command)
    if not parts:
        raise ValueError("Empty command")

    base_cmd = os.path.basename(parts[0])

    # If ALLOWED_COMMANDS is non-empty, enforce allowlist
    if ALLOWED_COMMANDS and base_cmd not in ALLOWED_COMMANDS:
        raise PermissionError(f"Command '{base_cmd}' is not in the allowed commands list")

    try:
        proc = subprocess.run(
            parts,
            cwd=WORKING_DIR,
            capture_output=True,
            text=True,
            timeout=request.timeout or 60,
        )
        stdout = proc.stdout
        stderr = proc.stderr
        returncode = proc.returncode
    except subprocess.TimeoutExpired as e:
        stdout = e.stdout or ""
        stderr = (e.stderr or "") + f"\nCommand timed out after {request.timeout or 60}s"
        returncode = -124
    except Exception as e:
        stdout = ""
        stderr = str(e)
        returncode = -1

    resp = ExecResponse(
        stdout=stdout,
        stderr=stderr,
        returncode=returncode,
        executed_command=request.command,
        working_dir=WORKING_DIR,
    )

    logger.debug("Exec command response: %s", resp.model_dump_json())
    return resp


@mcp.custom_route("/health", methods=["GET"])
def health_check(request: Request) -> PlainTextResponse:
    return PlainTextResponse("OK")
