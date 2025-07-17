from fastapi import FastAPI
from pydantic import BaseModel
from knowledgexpert.expert import handle_question, init as expert_init

app = FastAPI()
args = None  # Declare globals

def init(args_dict):
    global args
    # Simulate argparse.Namespace from dict
    class ArgsNamespace:
        def __init__(self, d):
            self.__dict__.update(d)
    args = ArgsNamespace(args_dict)
    # print("Args attributes:", vars(args))
    expert_init(args)  # Initialize knowledge_expert globals

import json
import os

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
    result = handle_question(request.query, request.session_id, args)
    return {"result": str(result)}
