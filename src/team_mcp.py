import os
import json
import logging
from fastmcp import FastMCP
from pydantic import BaseModel, Field
from expert_cli import parse_args as default_values
from knowledgexpert.team import Team
from knowledgexpert.util import resolve_env_vars
from knowledgexpert.structures import AnalystOutput, CodingOutput, TestingOutput
import team_cli as team_cli
from starlette.requests import Request
from starlette.responses import PlainTextResponse

class QueryRequest(BaseModel):
    query: str = Field(description='A query or a request from the user')
    session_id: str | None = Field(None, description='a session id to identify the user')

class TeamResponse(BaseModel):
    analystOutput: AnalystOutput = Field(description="Output from the system analyst agent")
    developerOutput: CodingOutput | None = Field(None, description="Output from the software developer agent if the request was to generate code")
    testerOutput: TestingOutput | None = Field(None,description="Output from the test developer agent if the request was to generate code or generate tests")
    fileWriterOutput: dict | None = Field(None, description="If files were added or updated, the file name and the content is provided in this field")

def init_team(args_dict):
    args_dict = resolve_env_vars(args_dict)
    default_args = vars(team_cli.parse_args([]))
    args = default_args
    args.update(args_dict)
    logger.info("Team args: %s", args)
    return Team(logger, vars(default_values([])), **args)

logger = logging.getLogger()

with open(os.path.join(os.path.expanduser("~"), ".knowledgexpert", "conf", "team", "config-mcp.json"), "r") as f:
    team_config = json.load(f)

knowledge_team = init_team(team_config)

def build_team_response(response: dict) -> TeamResponse:
    return TeamResponse(
        analystOutput=response.get("analyst_output"),        
        developerOutput=response.get("developer_output"),
        testerOutput=response.get("tester_output"),
        fileWriterOutput=response.get("file_writer_output")
    )

mcp = FastMCP(name="Team MCP Server")

@mcp.tool(name="knowledgeTeam", description="Multi-purpose tool that (1)answer user's questions about the Knowledgenet rules engine, (2) Generates code and test data when user requests it")
def team(request: QueryRequest) -> TeamResponse:
    logger.debug(
        f"Received team query: {request.query}, session_id: {request.session_id}")
    response = knowledge_team.handle_request(request.query, request.session_id)
    return build_team_response(response)

@mcp.custom_route("/health", methods=["GET"])
def health_check(request: Request) -> PlainTextResponse:
    return PlainTextResponse("OK")

