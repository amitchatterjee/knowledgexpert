
import logging
import argparse
import os
import sqlite3
import time
import uuid
from rich.console import Console
from prompt_toolkit import prompt
from prompt_toolkit.history import FileHistory
from langgraph.checkpoint.sqlite import SqliteSaver

from knowledgexpert.bookworm import BookWorm
from raven_cli import parse_args as default_values


def parse_args(args_list=None):
    parser = argparse.ArgumentParser(description="BookWorm LLM Assistant")
    parser.add_argument("--log", default="INFO", choices=[
                        "DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"], help="Set log level (default: INFO)")
    parser.add_argument("--confDir", default=os.path.join(os.path.expanduser("~"), ".knowledgexpert", "conf",
                        "bookworm"), help="Directory containing configurations (default: ~/.knowledgexpert/conf/bookworm)")
    parser.add_argument("--documents", nargs='+', type=str, required=True,
                        help="List of documents to study. This arg must be in the format: dir_path;glob_pattern,... The system will process all files of type - python and md, located under the directory specified by dir_path", default=[])
    parser.add_argument("--chunkSize", type=int,
                        default=20000, help="Chunk size for splitters")
    parser.add_argument("--chunkOverlap", type=int, default=0,
                        help="Chunk overlap for splitters (tokens)")
    parser.add_argument("--checkpointerDir", default=None,
                        help="Directory where checkpointer data is stored. Default: None")
    parser.add_argument("--input", default=None,
                        help="Input text to invoke the assistant with")

    if args_list is not None:
        return parser.parse_args(args_list)
    else:
        return parser.parse_args()


def serve_cli(args, logger, bookworm):
    console = Console()
    user_id = os.environ.get("USER", "Unknown")
    session = f"{user_id}-{bookworm.raven_args['persona']}-{int(time.time())}-{uuid.uuid4().hex}"
    history_file = os.path.join(os.path.expanduser(
        "~"), ".knowledgexpert", "history", "bookworm.history")
    input_arg = getattr(args, "input", None)
    if not input_arg:
        try:
            history_dir = os.path.dirname(history_file)
            os.makedirs(history_dir, exist_ok=True)
            if not os.path.exists(history_file):
                open(history_file, "a").close()
                logger.debug(f"Created history file at {history_file}")
        except Exception as e:
            logger.warning(
                f"Could not ensure history file {history_file}: {e}")
        history = FileHistory(history_file)
        console.print("BookWorm CLI. Type 'exit' to quit.")

    while True:
        if input_arg:
            user_query = input_arg
        else:
            user_query = prompt(f"\n{user_id}:> ", history=history).strip()
            if user_query.lower() in ("exit", "quit"):
                console.print("Goodbye!")
                return
            if not user_query:
                continue
            console.print(
                'The assistant is collecting information and processing them to come up with an answer...')

        response = bookworm.invoke(
            user_query, user_id, session, args.documents)
        for idx, element in enumerate(response):
            logger.debug(f"BookWormOutput[{idx}]:\n{element}")
        console.print(response[-1] if len(response) >
                      0 else 'No information found')
        if input_arg:
            break


if __name__ == "__main__":
    args = parse_args()
    log_level = getattr(logging, args.log.upper(), logging.INFO)
    logging.basicConfig(
        level=log_level, format='%(asctime)s %(levelname)s %(message)s')
    logger = logging.getLogger("Bookworm")
    dict_args = vars(args)

    checkpointer = None
    if args.checkpointerDir:
        os.makedirs(args.checkpointerDir, exist_ok=True)
        conn = sqlite3.connect(os.path.join(
            args.checkpointerDir, 'checkpointer.sqlite'), check_same_thread=False)
        checkpointer = SqliteSaver(conn)

    bookworm = BookWorm(logger, vars(default_values([])),
                        checkpointer, **dict_args)
    serve_cli(args, logger, bookworm)
