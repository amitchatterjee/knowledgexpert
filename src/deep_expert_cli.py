import logging
import argparse
import re

from knowledgexpert.experts_graph import ExpertsGraph
from knowledgexpert.expert import Expert
from expert_cli import parse_args as default_values
import os
import json

def parse_args(args_list=None):
    parser = argparse.ArgumentParser(description="ExpertsGraph LLM Assistant")
    parser.add_argument("--llmModel", default='openai:deepseek-r1-671b', help="LLM model (default: openai:deepseek-r1-671b)")
    parser.add_argument("--llmApiEndpoint", default='https://api.lambda.ai/v1', help="LLM API endpoint (default: https://api.lambda.ai/v1)")
    parser.add_argument("--format", choices=["raw", "structured"], default="structured", help="Output format: 'raw' or 'structured' (default: structured)")
    parser.add_argument("--log", default="INFO", choices=["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"], help="Set log level (default: INFO)")
    parser.add_argument("--confDir", default=os.path.join(os.path.expanduser("~"), ".knowledgexpert", "conf", "deep-expert"), help="Directory containing configurations (default: ~/.knowledgexpert/conf/deep-expert)")
    if args_list is not None:
        return parser.parse_args(args_list)
    else:
        return parser.parse_args()

def process(args, logger, graph):
    user_query = input("Enter your question: ")
    name = os.environ.get("USER", "Unknown")
    response = graph.handle_question(user_query, name)
    print("Response:", response)

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
        else:
            resolved[k] = v
    return resolved

def init_expert(logger, args, type):
    config_path = os.path.join(args.confDir, type, "config.json")
    with open(config_path, "r") as f:
        expert_config = json.load(f)
    args_dict = resolve_env_vars(expert_config)
    default_args = default_values([])
    args = ArgsNamespace(args_dict)
    # Merge default_args with args, with args overriding default_args
    merged_args = vars(default_args)
    merged_args.update(args_dict)
    args = ArgsNamespace(merged_args)
    
    return Expert(args, logger)

if __name__ == "__main__":
    args = parse_args()
    logging.basicConfig(level=getattr(logging, args.log))
    logger = logging.getLogger("ExpertsGraph")

    coding_expert = init_expert(logger, args, "coding-expert")

    graph = ExpertsGraph(args, logger, coding_expert=coding_expert)
    process(args, logger, graph)