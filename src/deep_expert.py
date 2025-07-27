import logging
import argparse

from knowledgexpert.experts_graph import ExpertsGraph

def parse_args(args_list=None):
    parser = argparse.ArgumentParser(description="ExpertsGraph LLM Assistant")
    parser.add_argument("--llmModel", default='openai:deepseek-r1-671b', help="LLM model (default: openai:deepseek-r1-671b)")
    parser.add_argument("--llmApiEndpoint", default='https://api.lambda.ai/v1', help="LLM API endpoint (default: https://api.lambda.ai/v1)")
    parser.add_argument("--format", choices=["raw", "structured"], default="structured", help="Output format: 'raw' or 'structured' (default: structured)")
    parser.add_argument("--log", default="INFO", choices=["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"], help="Set log level (default: INFO)")
    if args_list is not None:
        return parser.parse_args(args_list)
    else:
        return parser.parse_args()

def process(args, logger):
    graph = ExpertsGraph(args, logger)
    user_query = input("Enter your question: ")
    name = input("Enter your name: ")
    response = graph.handle_question(user_query, name)
    print("Response:", response)

if __name__ == "__main__":
    args = parse_args()
    logging.basicConfig(level=getattr(logging, args.log))
    logger = logging.getLogger("ExpertsGraph")

    process(args, logger)