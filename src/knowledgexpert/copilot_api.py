from fastapi import FastAPI
from pydantic import BaseModel
from knowledgexpert.expert import handle_question, init as expert_init, parse_args
import logging
import json
import os

'''
Copilot Chat participant backend
'''

app = FastAPI()
args = None 
logger = logging.getLogger()

def init(args_dict):
    global args
    # Simulate argparse.Namespace from dict
    class ArgsNamespace:
        def __init__(self, d):
            self.__dict__.update(d)
        def __str__(self):
            return f"{self.__class__.__name__}({', '.join(f'{k}={v}' for k, v in self.__dict__.items())})"
        def __repr__(self):
            return __self.__str()
        
    default_args = parse_args([])
    args = ArgsNamespace(args_dict)
    # Merge default_args with args, with args overriding default_args
    merged_args = vars(default_args)
    merged_args.update(args_dict)
    args = ArgsNamespace(merged_args)
    log_level = getattr(logging, args.log.upper(), logging.INFO)
    logging.basicConfig(level=log_level, format='%(asctime)s %(levelname)s %(message)s')
    logger.info("Args: %s", args)
    expert_init(args, logger)

# Load configuration from a JSON file
knowledgexpert_conf = os.path.join(os.path.expanduser("~"), ".knowledgexpert", "conf", "config.json")
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
    result = handle_question(request.query, request.session_id, args)
    logger.debug(f"handle_question result: {result}")
    return {"result": str(result)}
