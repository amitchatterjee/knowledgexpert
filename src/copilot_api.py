from fastapi import FastAPI
from pydantic import BaseModel
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

app = FastAPI()
args = None 
logger = logging.getLogger()

# Simulate argparse.Namespace from dict
class ArgsNamespace:
    def __init__(self, d):
        self.__dict__.update(d)
    def __str__(self):
        return f"{self.__class__.__name__}({', '.join(f'{k}={v}' for k, v in self.__dict__.items())})"
    def __repr__(self):
        return self.__str()

def replacer(match):
    env_var = match.group(1)
    return os.environ.get(env_var, "")

def resolve_env_vars(args_dict: dict[str, str]) -> dict[str, str]:
    # Replace any string values in args_dict with environment variables if specified as ${ENV}
    pattern = re.compile(r"\$\{([^}]+)\}")
    resolved = {}
    for k, v in args_dict.items():
        if isinstance(v, str):
            print(k, '=', v)
            #print(pattern.findall(v))
            resolved[k] = pattern.sub(replacer, v)
    return resolved

def init(args_dict:dict[str,any]):
    global args, expert
    args_dict = resolve_env_vars(args_dict)
    default_args = parse_args([])
    args = ArgsNamespace(args_dict)
    # Merge default_args with args, with args overriding default_args
    merged_args = vars(default_args)
    merged_args.update(args_dict)
    args = ArgsNamespace(merged_args)
    log_level = getattr(logging, args.log.upper(), logging.INFO)
    logging.basicConfig(level=log_level, format='%(asctime)s %(levelname)s %(message)s')
    logger.info("Args: %s", args)
    expert = Expert(args, logger)

# Load configuration from a JSON file
knowledgexpert_conf = os.path.join(os.path.expanduser("~"), ".knowledgexpert", "conf", "copilot", "config.json")
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
