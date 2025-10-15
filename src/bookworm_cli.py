import logging
import argparse
import os

from knowledgexpert.bookworm import BookWorm
from expert_cli import parse_args as default_values

def parse_args(args_list=None):
    parser = argparse.ArgumentParser(description="BookWorm LLM Assistant")
    parser.add_argument("--log", default="INFO", choices=["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"], help="Set log level (default: INFO)")
    parser.add_argument("--confDir", default=os.path.join(os.path.expanduser("~"), ".knowledgexpert", "conf", "bookworm"), help="Directory containing configurations (default: ~/.knowledgexpert/conf/bookworm)")
    parser.add_argument("--documents", nargs='+', type=str, required=True, help="List of documents to study. This arg must be in the format: dir_path;glob_pattern,... The system will process all files of type - python and md, located under the directory specified by dir_path", default=[])
    parser.add_argument("--chunkSize", type=int, default=20000, help="Chunk size for splitters")
    parser.add_argument("--chunkOverlap", type=int, default=0, help="Chunk overlap for splitters (tokens)")
    
    if args_list is not None:
        return parser.parse_args(args_list)
    else:
        return parser.parse_args()

def process(args, logger, bookworm):
    user_query = input("Enter your question: ")
    name = os.environ.get("USER", "Unknown")
    response = bookworm.handle_question(user_query, name, args.documents)
    for idx, element in enumerate(response):
        logger.debug(f"BookWormOutput[{idx}]:\n{element}")
    print(response[-1] if len(response) > 0 else 'No information found')
    
if __name__ == "__main__":
    args = parse_args()
    log_level = getattr(logging, args.log.upper(), logging.INFO)
    logging.basicConfig(level=log_level, format='%(asctime)s %(levelname)s %(message)s')
    logger = logging.getLogger("BookWorm")
    dict_args = vars(args)
    bookworm = BookWorm(logger, vars(default_values([])), **dict_args)
    process(args, logger, bookworm)
