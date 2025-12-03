import os
import json
import logging
from fastmcp import FastMCP
from pydantic import BaseModel, Field
from raven_cli import parse_args as default_values
from knowledgexpert.wolfpack import Wolfpack
from knowledgexpert.util import resolve_env_vars
from knowledgexpert.structures import AnalystOutput, CodingOutput, TestingOutput
import wolfpack_cli
from starlette.requests import Request
from starlette.responses import PlainTextResponse

class QueryRequest(BaseModel):
    query: str = Field(description='A query or a request from the user')
    session_id: str | None = Field(None, description='a session id to identify the user')

class WolfpackResponse(BaseModel):
    analystOutput: AnalystOutput = Field(description="Output from the system analyst agent")
    developerOutput: CodingOutput | None = Field(None, description="Output from the software developer agent if the request was to generate code")
    testerOutput: TestingOutput | None = Field(None,description="Output from the test developer agent if the request was to generate code or generate tests")
    fileWriterOutput: dict | None = Field(None, description="If files were added or updated, the file name and the content is provided in this field")

def init_wolfpack(args_dict):
    args_dict = resolve_env_vars(args_dict)
    default_args = vars(wolfpack_cli.parse_args([]))
    args = default_args
    args.update(args_dict)
    logger.info("Wolfpack args: %s", args)
    return Wolfpack(logger, vars(default_values([])), **args)

logger = logging.getLogger()

with open(os.path.join(os.path.expanduser("~"), ".knowledgexpert", "conf", "wolfpack", "config-mcp.json"), "r") as f:
    wolfpack_config = json.load(f)

wolfpack = init_wolfpack(wolfpack_config)

def build_wolfpack_response(response: dict) -> WolfpackResponse:
    return WolfpackResponse(
        analystOutput=response.get("analyst_output"),        
        developerOutput=response.get("developer_output"),
        testerOutput=response.get("tester_output"),
        fileWriterOutput=response.get("file_writer_output")
    )

mcp = FastMCP(name="Wolfpack MCP Server")

@mcp.tool(name="Wolfpack", description="Multi-purpose tool that (1)answer user's questions about the Knowledgenet rules engine, (2) Generates code and test data when user requests it")
def request_wolfpack(request: QueryRequest) -> WolfpackResponse:
    logger.debug(
        f"Received Wolfpack query: {request.query}, session_id: {request.session_id}")
    response = wolfpack.invoke(request.query, request.session_id)
    return build_wolfpack_response(response)

@mcp.custom_route("/health", methods=["GET"])
def health_check(request: Request) -> PlainTextResponse:
    return PlainTextResponse("OK")

