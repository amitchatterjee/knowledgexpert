from typing import Optional
from fastapi import FastAPI
from pydantic import BaseModel, Field
from knowledgexpert.expert import Expert
from expert_cli import parse_args
import logging
import json
import os
import re

# NOTE the API_KEY environment variable specific to LLM/Embedding provider must be set for this application to work


'''
Copilot Chat participant backend
'''

# This may not be needed as we are using raw format (in the configuration) for copilot service
class CodingAdvice(BaseModel):
    summary: Optional[str] = Field("A one-line summary of the code snippet")
    description: Optional[str] = Field(
        description="Description of the code snippet")
    code: str = Field(description="A Python Code Snippet")
    explanation: Optional[str] = Field(
        description="Detailed explaination of the code")
    references: Optional[list] = Field(
        description="A list of URLs containing more information")

app = FastAPI()
args = None 
logger = logging.getLogger()

def replacer(match):
    env_var = match.group(1)
    return os.environ.get(env_var, "")

def resolve_env_vars(args_dict: dict[str, str]) -> dict[str, str]:
    # Replace any string values in args_dict with environment variables if specified as ${ENV}
    pattern = re.compile(r"\$\{([^}]+)\}")
    resolved = {}
    for k, v in args_dict.items():
        if isinstance(v, str):
            #print(k, '=', v)
            #print(pattern.findall(v))
            resolved[k] = pattern.sub(replacer, v)
        else:
            resolved[k] = v
    return resolved

def init(args_dict:dict[str,any]):
    global expert
    args_dict = resolve_env_vars(args_dict)
    default_args = vars(parse_args([]))
    # Merge default_args with args, with args overriding default_args
    args = default_args
    args.update(args_dict)
    log_level = getattr(logging, args["log"].upper(), logging.INFO)
    logging.basicConfig(level=log_level, format='%(asctime)s %(levelname)s %(message)s')
    logger.info("Args: %s", args)
    expert = Expert(logger, structure=CodingAdvice, **args)

# Load configuration from a JSON file
knowledgexpert_conf = os.path.join(os.path.expanduser("~"), ".knowledgexpert", "conf", "expert", "config.json")
config_path = knowledgexpert_conf if knowledgexpert_conf and os.path.isfile(knowledgexpert_conf) else "config.json"
with open(config_path, "r") as f:
    config = json.load(f)

init(config)

class QueryRequest(BaseModel):
    query: str
    session_id: str

@app.post("/ask")
def ask(request: QueryRequest):
    logger.debug(f"Received query: {request.query}, session_id: {request.session_id}")
    result = expert.handle_question(request.query, request.session_id)
    logger.debug(f"handle_question result: {result}")
    return {"result": str(result)}
