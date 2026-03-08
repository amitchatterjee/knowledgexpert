# Utility function to format a lower camel case string as described
import re
from fastapi import FastAPI
from pydantic import BaseModel
import logging
import json
import os

import raven_cli
import wolfpack_cli as wolfpack_cli
from raven_cli import parse_args as default_values
from knowledgexpert.wolfpack import Wolfpack
from knowledgexpert.util import resolve_env_vars
from knowledgexpert.structures import AnalystOutput, CodingOutput, TestingOutput

def init(wolfpack_args_dict:dict[str,any]):
    global wolfpack
    wolfpack = init_wolfpack(wolfpack_args_dict)

def init_wolfpack(args_dict):
    args_dict = resolve_env_vars(args_dict)
    default_args = vars(wolfpack_cli.parse_args([]))
    args = default_args
    args.update(args_dict) 
    logger.info("Wolfpack args: %s", args)
    return Wolfpack(logger, vars(default_values([])), **args)

app = FastAPI()
logger = logging.getLogger()

with open(os.path.join(os.path.expanduser("~"), ".knowledgexpert", "conf", "wolfpack", "config-copilot.json"), "r") as f:
    wolfpack_config = json.load(f)

init(wolfpack_config)

class QueryRequest(BaseModel):
    query: str
    session_id: str

def format_lower_camel_case(s: str) -> str:
    # Tokenize by case boundary
    tokens = re.findall(r'[A-Z]?[a-z]+|[A-Z]+(?![a-z])', s)
    # Convert each token to upper camel case
    tokens = [token.capitalize() for token in tokens]
    # Join with space
    return ' '.join(tokens)

def format_analyst_output(analyst_output: AnalystOutput) -> str:
    lines = []
    for field, value in analyst_output.__dict__.items():
        if value is None or value == '' or value == []:
            continue
        if field == 'references' and value:
            lines.append(f"### {format_lower_camel_case(field)}:\n" + '\n'.join(f"- {ref}" for ref in value))
        else:
            lines.append(f"### {format_lower_camel_case(field)}:\n\n")
            lines.append(f"{value}")
    return '\n\n'.join(lines)

def format_coder_output(coding_output: CodingOutput) -> str:
    lines = []
    for field, value in coding_output.__dict__.items():
        if value is None or value == '' or value == []:
            continue
        if field == 'references' and value:
            lines.append(f"### {format_lower_camel_case(field)}:\n" + '\n'.join(f"- {ref}" for ref in value))
        elif field == 'code' and value:
            lines.append(f"### {format_lower_camel_case(field)}:\n\n```python\n{value}\n```")
        else:
            lines.append(f"### {format_lower_camel_case(field)}:\n\n")
            lines.append(f"{value}")
    return '\n\n'.join(lines)

def format_tester_output(tester_output: TestingOutput) -> str:
    lines = []
    for field, value in tester_output.__dict__.items():
        if value is None or value == '' or value == []:
            continue
        if field == 'references' and value:
            lines.append(f"### {format_lower_camel_case(field)}:\n" + '\n'.join(f"- {ref}" for ref in value))
        elif field == 'content' and value:
            # value is a list of TestFileOutput
            for file_output in value:
                ext = os.path.splitext(file_output.fileName)[1].lower()
                if ext == '.csv':
                    codeblock = 'csv'
                elif ext == '.json':
                    codeblock = 'json'
                elif ext == '.edi':
                    codeblock = 'edi'
                else:
                    codeblock = ''
                lines.append(f"#### {file_output.fileName}\n\n```{codeblock}")
                lines.append(f"{file_output.content}\n```")
        else:
            lines.append(f"### {format_lower_camel_case(field)}:\n\n")
            lines.append(f"{value}")
    return '\n\n'.join(lines)

def format_file_writer_output(response:dict)->str:
    files = sorted(response["files"])
    return "### Files Added/Updated:\n\n" + '\n'.join(f"- [{os.path.basename(file)}]({file})" for file in files)

def format_response(response:dict)->str:
    result = '## Analyst Output:\n\n'
    result += format_analyst_output(response["analyst_output"])
    if "developer_output" in response:
        result += f"\n\n---\n\n## Developer Output:\n\n{format_coder_output(response["developer_output"])}"
    if "tester_output" in response:
        result += f"\n\n---\n\n## Tester Output:\n\n{format_tester_output(response["tester_output"])}" 
    if "file_writer_output" in response:
        result += f"\n\n---\n\n## File Writer Tool Output:\n\n{format_file_writer_output(response["file_writer_output"])}"
    return result

@app.post("/ask/wolfpack")
def ask_wolfpack(request: QueryRequest):
    logger.debug(f"Received wolfpack query: {request.query}, session_id: {request.session_id}")
    response = wolfpack.invoke(request.query, request.session_id, thread_id=request.session_id)
    return {"result": format_response(response)}
