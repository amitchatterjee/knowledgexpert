import argparse
import importlib
import json
import logging
import os
import sqlite3
import sys
from rich.console import Console
from prompt_toolkit import prompt
from prompt_toolkit.history import FileHistory
from langgraph.checkpoint.sqlite import SqliteSaver

from knowledgexpert.raven import Raven
from knowledgexpert.util import embedding_mapper, resolve_env_vars
import uuid
import time

def parse_args(args_list=None):
    parser = argparse.ArgumentParser(description="Raven CLI")

    # LLM-related stuff
    parser.add_argument("--llmModel", help="LLM model identifier")
    parser.add_argument("--llmApiEndpoint", default=None, help="LLM API endpoint")

    # Prompt-related stuff
    parser.add_argument("--promptDir", default=os.path.join(os.path.expanduser("~"), ".knowledgexpert", "conf", "raven"), help="Directory containing prompt templates (default: ~/.knowledgexpert/conf/prompt)")
    parser.add_argument("--checkpointerDir", default=None, help="Directory where checkpointer data is stored. Default: None")

    # Options
    parser.add_argument("--skipRetrieval", action="store_true", help="Skip vector database retrieval and send the prompt directly to the LLM (default: False)")
    parser.add_argument("--retrievalType", choices=["2stepRag", "agenticRag"], default="agenticRag", help="Specify what style of vector retrieval is needed. Default: 'agentic'") 
    parser.add_argument("--skipMcpTools", action="store_true", help="Skip MCP tools use and send the prompt directly to the LLM (default: False)")

    # Vector-related stuff
    parser.add_argument("--embeddingApiUrl", default=None, help="Default URL for the embedding server (optional)")
    parser.add_argument("--embeddingModel", default='msmarco-MiniLM-L6-v3', help="Default embedding model (default: msmarco-MiniLM-L6-v3)")
    parser.add_argument("--embeddingProvider", default='ollama', choices=['openai', 'ollama'], help="Default embedding provider (default: ollama)")
    parser.add_argument("--embeddings", nargs='+', default=[None], help='Embeddings used for this application. Accepts one or more values. Each value is of the format: <embedding_id>:[embedding_url][|][embedding_model][|][k][|][score_threshold][|][embedding_id]')
    parser.add_argument("--chromaHost", default='localhost', help="ChromaDB host (default: localhost)")
    parser.add_argument("--chromaPort", type=int, default=8000, help="ChromaDB port (default: 8000)")
    parser.add_argument("--baseCollections", nargs='+', default=['all_collection'], help='Base collection names (default: all_collection). Accepts one or more values. Each value is of the format: <collection_name>[|][search_algorithm][|][k][|][score_threshold]')
    parser.add_argument("--searchAlgorithm", type=str, default="similarity", help="Default search algorithm for retriever (e.g., 'similarity', 'mmr', etc.)")
    parser.add_argument("--scoreThreshold", type=float, default=None, help="Default score threshold for similarity_score_threshold search (optional)")
    parser.add_argument("--k", type=int, default=None, help="Default k (nearest neighbor) value")
    
    parser.add_argument("--ensembleWeights", nargs=2, type=float, default=[], help="Weights for ensemble retriever (default: [])")
    parser.add_argument("--vectorToolName", default="AutoDoc", help="If agentic RAG option is selected, the name of the vector tool")
    parser.add_argument("--vectorToolDescription", default="Search and return information from the company vector db", help="If agentic RAG option is selected, the description for the vector tool")
    parser.add_argument("--persona", default="Raven", help="Persona name to use as input parameter (default: Raven)")
    parser.add_argument("--reactLoopMax", type=int, default=25, help="Max ReAct tool-call loops (LangGraph recursion_limit). Default: 25")

    # MCP-related stuff
    parser.add_argument("--mcpConfig", help="Path to MCP config JSON")
    parser.add_argument("--mcpInsecure", action="store_true", help="Disable TLS verification for MCP")

    # General configuration
    parser.add_argument("--confDir", default=None, help="Directory containing config.json for base configuration (optional)")

    parser.add_argument("--log", default="INFO", choices=["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"], help="Set log level (default: INFO)")

    parser.add_argument("--outputType", default=None, help="Fully qualified type name for response (default: None)")

    parser.add_argument("--input", default=None, help="Input text to invoke the agent with")
    parser.add_argument("--context", default=None, help="A string that is used to pass on additional context (default: '')")

    args = None
    if args_list is not None:
        args = parser.parse_args(args_list)
    else:
        args = parser.parse_args()

    collections_list = []
    for base_collection in args.baseCollections:
        collections_list.append(collections_mapper(base_collection, args.searchAlgorithm, args.k, args.scoreThreshold))
    args.baseCollections = collections_list
    for attr in ["searchAlgorithm", "k", "scoreThreshold"]:
        if hasattr(args, attr):
            delattr(args, attr)

    embeddings_list = []
    for embedding in args.embeddings:
        embeddings_list.append(embedding_mapper(
            embedding, args.embeddingProvider,args.embeddingApiUrl, args.embeddingModel))
    args.embeddings = embeddings_list
    for attr in ["embeddingProvider","embeddingApiUrl","embeddingModel"]:
        if hasattr(args, attr):
            delattr(args, attr)

    if args.outputType:
        module_name, class_name = args.outputType.rsplit('.', 1)
        structure_module = importlib.import_module(module_name)
        args.outputType = getattr(structure_module, class_name)
    #else:
    #    args.outputType = Answer

    return args

def collections_mapper(base_collection, default_search_algorithm, default_k,default_score_threshold):
    tokens = base_collection.split('|')
    collection_name = tokens[0]
    search_alg = tokens[1] if len(tokens) > 1 and tokens[1] else default_search_algorithm
    k_val = int(tokens[2]) if len(tokens) > 2 and tokens[2] else default_k
    score_thresh = float(tokens[3]) if len(tokens) > 3 and tokens[3] else default_score_threshold
    embedding_id = tokens[4] if len(tokens) > 4 and tokens[4] else 'default'
    to_dict = {'collectionName': collection_name, "searchAlgorithm": search_alg, "k": k_val, "scoreThreshold": score_thresh, "embeddingId": embedding_id}
    return to_dict

def serve_cli(raven, logger, persona, is_checkpointer, input, extra_context=None):
    console = Console()
    user_id = os.environ.get("USER") or os.environ.get("USERNAME") or "user"
    prompt_history_file = os.path.join(os.path.expanduser("~"), ".knowledgexpert", "history", "raven.history")
    session = f"{user_id}-{persona}-{int(time.time())}-{uuid.uuid4().hex}"
    logger.debug("Session id: %s", session)
    if not input:
        try:
            history_dir = os.path.dirname(prompt_history_file)
            os.makedirs(history_dir, exist_ok=True)
            if not os.path.exists(prompt_history_file):
                open(prompt_history_file, "a").close()
                logger.debug("Created history file: %s", prompt_history_file)
        except Exception as e:
            logger.warning(f"Could not ensure history file: %s. Error: %s", prompt_history_file, e)
        history = FileHistory(prompt_history_file)
        console.print("Raven CLI. Type 'exit' to quit.")
    while True:
        if input:
            user_query = input
        else:
            user_query = prompt(f"\n{user_id}:> ", history=history).strip()
            if user_query.lower() in {"exit", "quit"}:
                console.print("Goodbye!")
                break
            if not user_query:
                continue
            console.print('The assistant is collecting information and processing them to come up with an answer...')

        config = {"configurable": {"thread_id": session}} if is_checkpointer else {}
        if getattr(raven.args, "reactLoopMax", None):
            config["recursion_limit"] = raven.args.reactLoopMax
        request = {"messages": [{"role": "user", "content": user_query}],
                   "user_id": user_id, "persona": persona}
        context = {'document': extra_context} if extra_context else {}
        result = raven.invoke(request, config=config, context=context)
        console.print("Raven Assistant: Here is my response. I make mistakes. So, please double-check my answers.")
        console.print(result)
        if input:
            break

if __name__ == "__main__":
    args = parse_args()

    base_config = {}
    if args.confDir:
        config_path = os.path.join(args.confDir, "config.json")
        with open(config_path, "r") as f:
            base_config = json.load(f)
            base_config = resolve_env_vars(base_config)
            delattr(args, "confDir")
    
    merged_config = base_config.copy()
    for k, v in vars(args).items():
        if k not in merged_config:
            merged_config[k] = v
        elif v is not None and not merged_config[k]:
            merged_config[k] = v

    log_level = getattr(logging, merged_config["log"].upper(), logging.INFO)
    logging.basicConfig(level=log_level, format='%(asctime)s %(levelname)s %(message)s')
    logger = logging.getLogger('knowledgexpert')
    print("Note: If you are using a commercial LLM, make sure you have the necessary environment variable with the secret")
    logger.info("Initializing Raven using parameters: %s", merged_config)

    checkpointer = None
    if args.checkpointerDir:
        os.makedirs(args.checkpointerDir, exist_ok=True)
        conn = sqlite3.connect(os.path.join(args.checkpointerDir, 'checkpointer.sqlite'), check_same_thread=False)
        checkpointer = SqliteSaver(conn)

    try:
        raven = Raven(logger, structure=args.outputType, checkpointer=checkpointer, **merged_config)
        serve_cli(raven, logger, args.persona, checkpointer != None, args.input, args.context)

    except Exception as e:
        logger.exception("Failed to run Raven: %s", e)
        sys.exit(1)