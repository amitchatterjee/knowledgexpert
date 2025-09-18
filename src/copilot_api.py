from typing import Optional
from fastapi import FastAPI
from pydantic import BaseModel, Field
from knowledgexpert.expert import Expert
from expert_cli import parse_args
import logging
import json
import os

# NOTE the API_KEY environment variable specific to LLM/Embedding provider must be set for this application to work

'''
Copilot Chat participant backend
'''
from knowledgexpert.util import resolve_env_vars
from knowledgexpert.structures import CodingAdvice

app = FastAPI()
args = None 
logger = logging.getLogger()

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
