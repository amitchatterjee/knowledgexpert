import logging
import argparse

from knowledgexpert.team import Team
from expert_cli import parse_args as default_values
import os

def parse_args(args_list=None):
    parser = argparse.ArgumentParser(description="Team LLM Assistant")
    parser.add_argument("--log", default="INFO", choices=["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"], help="Set log level (default: INFO)")
    parser.add_argument("--confDir", default=os.path.join(os.path.expanduser("~"), ".knowledgexpert", "conf", "team"), help="Directory containing configurations (default: ~/.knowledgexpert/conf/team)")
    parser.add_argument("--workspaceDir", default=os.path.join(os.path.expanduser("~"), ".knowledgexpert", "workspace", "team"), help="Directory for workspace (default: ~/.knowledgexpert/workspace/team)")
    parser.add_argument('--requestPath', type=str, default=None, help='Path to file containing the request/query')
    parser.add_argument('--skipWriter', action='store_true', help='Skip writing files to disk (default: False)')
    if args_list is not None:
        return parser.parse_args(args_list)
    else:
        return parser.parse_args()

def process(args, logger, graph):
    if getattr(args, 'requestPath', None):
        with open(args.requestPath, 'r', encoding='utf-8') as f:
            user_query = f.read().strip()
    else:
        user_query = input("Enter your question/request: ")
    name = os.environ.get("USER", "Unknown")
    response = graph.handle_request(user_query, name)
    for key, value in response.items():
        print(f"{key}:\n{'-'*20}\n{value}\n")

if __name__ == "__main__":
    args = parse_args()
    log_level = getattr(logging, args.log.upper(), logging.INFO)
    logging.basicConfig(level=log_level, format='%(asctime)s %(levelname)s %(message)s')
    logger = logging.getLogger("DeepExpert")
    dict_args = vars(args)
    graph = Team(logger, vars(default_values([])), **dict_args)
    process(args, logger, graph)