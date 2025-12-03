import logging
import argparse
import os
import sqlite3
import time
import uuid

from langgraph.checkpoint.sqlite import SqliteSaver

from knowledgexpert.wolfpack import Wolfpack
from raven_cli import parse_args as default_values
from rich.console import Console
from prompt_toolkit import prompt
from prompt_toolkit.history import FileHistory

def parse_args(args_list=None):
    parser = argparse.ArgumentParser(description="Wolfpack LLM Assistant")
    parser.add_argument("--log", default="INFO", choices=["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"], help="Set log level (default: INFO)")
    parser.add_argument("--confDir", default=os.path.join(os.path.expanduser("~"), ".knowledgexpert", "conf", "wolfpack"), help="Directory containing configurations (default: ~/.knowledgexpert/conf/wolfpack)")
    parser.add_argument("--workspaceDir", default=os.path.join(os.path.expanduser("~"), ".knowledgexpert", "workspace", "wolfpack"), help="Directory for workspace (default: ~/.knowledgexpert/workspace/wolfpack)")
    parser.add_argument('--requestPath', type=str, default=None, help='Path to file containing the request/query')
    parser.add_argument('--skipWriter', action='store_true', help='Skip writing files to disk (default: False)')
    parser.add_argument("--checkpointerDir", default=None, help="Directory where checkpointer data is stored. Default: None")
    if args_list is not None:
        return parser.parse_args(args_list)
    else:
        return parser.parse_args()

def serve_cli(args, logger, wolfpack):
    user_id = os.environ.get("USER", "Unknown")
    session = f"{user_id}-Wolfpack-{int(time.time())}-{uuid.uuid4().hex}"
    logger.debug("Session id: %s", session)

    console = Console()

    history_file = os.path.join(os.path.expanduser("~"), ".knowledgexpert", "history", "wolfpack.history")
    try:
        history_dir = os.path.dirname(history_file)
        os.makedirs(history_dir, exist_ok=True)
        if not os.path.exists(history_file):
            open(history_file, "a").close()
            logger.debug(f"Created history file at {history_file}")
    except Exception as e:
        logger.warning(f"Could not ensure history file {history_file}: {e}")
    history = FileHistory(history_file)

    user_query = None
    if getattr(args, 'requestPath', None):
        with open(args.requestPath, 'r', encoding='utf-8') as f:
            user_query = f.read().strip()
            console.print(f'Question/request: {user_query}')
    while True:
        if not user_query:
            user_query = prompt("Enter your question/request: ", history=history)
            user_query = user_query.strip()
            if user_query.lower() in {"exit", "quit"}:
                console.print("Goodbye!")
                break
            if not user_query:
                continue

        console.print('The assistant is collecting information and processing them to come up with an answer...')
        response = wolfpack.invoke(user_query, user_id, thread_id=session)
        for key, value in response.items():
            console.print(f"{key}:\n{'-'*20}\n{value}\n")
        user_query = None

if __name__ == "__main__":
    args = parse_args()
    log_level = getattr(logging, args.log.upper(), logging.INFO)
    logging.basicConfig(level=log_level, format='%(asctime)s %(levelname)s %(message)s')
    logger = logging.getLogger("Wolfpack")
    dict_args = vars(args)

    checkpointer = None
    if args.checkpointerDir:
        os.makedirs(args.checkpointerDir, exist_ok=True)
        conn = sqlite3.connect(os.path.join(args.checkpointerDir, 'checkpointer.sqlite'), check_same_thread=False)
        checkpointer = SqliteSaver(conn)

    wolfpack = Wolfpack(logger, vars(default_values([])), checkpointer=checkpointer, **dict_args)
    serve_cli(args, logger, wolfpack)