import logging
import argparse
import os

from knowledgexpert.wolfpack_legacy import Wolfpack
from expert_cli import parse_args as default_values
from prompt_toolkit import prompt
from prompt_toolkit.history import FileHistory

DEPRECATION_DISCLAIMER = (
    "[DEPRECATED] wolfpack_legacy_cli.py is a legacy CLI and may be removed in a future release."
)

def parse_args(args_list=None):
    parser = argparse.ArgumentParser(description="Wolfpack LLM Assistant")
    parser.add_argument("--log", default="INFO", choices=["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"], help="Set log level (default: INFO)")
    parser.add_argument("--confDir", default=os.path.join(os.path.expanduser("~"), ".knowledgexpert", "conf", "wolfpack"), help="Directory containing configurations (default: ~/.knowledgexpert/conf/wolfpack-legacy)")
    parser.add_argument("--workspaceDir", default=os.path.join(os.path.expanduser("~"), ".knowledgexpert", "workspace", "wolfpack"), help="Directory for workspace (default: ~/.knowledgexpert/workspace/wolfpack)")
    parser.add_argument('--requestPath', type=str, default=None, help='Path to file containing the request/query')
    parser.add_argument('--skipWriter', action='store_true', help='Skip writing files to disk (default: False)')
    if args_list is not None:
        return parser.parse_args(args_list)
    else:
        return parser.parse_args()

def process(args, logger, wolfpack):
    if getattr(args, 'requestPath', None):
        with open(args.requestPath, 'r', encoding='utf-8') as f:
            user_query = f.read().strip()
    else:
        history_file = os.path.join(os.path.expanduser("~"), ".knowledgexpert", "history", "wolfpack-legacy.history")
        try:
            history_dir = os.path.dirname(history_file)
            os.makedirs(history_dir, exist_ok=True)
            if not os.path.exists(history_file):
                open(history_file, "a").close()
                logger.debug(f"Created history file at {history_file}")
        except Exception as e:
            logger.warning(f"Could not ensure history file {history_file}: {e}")
        history = FileHistory(history_file)
        user_query = prompt("Enter your question/request: ", history=history)
        if not user_query or not user_query.strip():
            print("No query provided, exiting.")
            return
    name = os.environ.get("USER", "Unknown")
    response = wolfpack.handle_request(user_query, name)
    for key, value in response.items():
        print(f"{key}:\n{'-'*20}\n{value}\n")

if __name__ == "__main__":
    print(DEPRECATION_DISCLAIMER)
    args = parse_args()
    log_level = getattr(logging, args.log.upper(), logging.INFO)
    logging.basicConfig(level=log_level, format='%(asctime)s %(levelname)s %(message)s')
    logger = logging.getLogger("Wolfpack")
    dict_args = vars(args)
    wolfpack = Wolfpack(logger, vars(default_values([])), **dict_args)
    process(args, logger, wolfpack)