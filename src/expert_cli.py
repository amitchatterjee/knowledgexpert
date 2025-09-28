import os
import logging
from rich.console import Console
import argparse
import importlib
import json

from knowledgexpert.expert import Expert
from knowledgexpert.util import resolve_env_vars, embedding_mapper

# NOTE the API_KEY environment variable specific to LLM/Embedding provider must be set for this application to work

def print_structured_output(out, console):
    if out.summary:
        console.print(f'Summary: {out.summary}')
    if out.description:
        console.print(f'\nDescription: {out.description}')
    if out.code:
        console.print('\nCode:')
        console.print(out.code)
    if out.explanation:
        console.print(f'\nExplanation:\n {out.explanation}')
    if out.references:
        console.print('\nReferences:')
        for i in range(len(out.references)):
            console.print(f"{i+1}: {out.references[i]}")

def serve_cli(expert, interactions):
    console = Console()
    name = os.environ.get("USER") or os.environ.get("USERNAME") or "user"
    console.print("Knowledgenet assistant (Graph + Vector RAG). Type 'exit' to quit.")
    while True:
        user_query = input(f"\n{name}:> ").strip()
        if user_query.lower() in {"exit", "quit"}:
            console.print("Goodbye!")
            break
        if not user_query:
            continue
        console.print('The assistant is collecting information and processing them to come up with an answer...')
        out = expert.handle_question(user_query, name, interactions)
        console.print("Knowledge Assistant: Here is my response. I make mistakes. So, please double-check my answers.")
        console.print(out)

def collections_mapper(base_collection, default_search_algorithm, default_k,default_score_threshold):
    tokens = base_collection.split('|')
    collection_name = tokens[0]
    search_alg = tokens[1] if len(tokens) > 1 and tokens[1] else default_search_algorithm
    k_val = int(tokens[2]) if len(tokens) > 2 and tokens[2] else default_k
    score_thresh = float(tokens[3]) if len(tokens) > 3 and tokens[3] else default_score_threshold
    embedding_id = tokens[4] if len(tokens) > 4 and tokens[4] else 'default'
    to_dict = {'collectionName': collection_name, "searchAlgorithm": search_alg, "k": k_val, "scoreThreshold": score_thresh, "embeddingId": embedding_id}
    return to_dict


def parse_args(args_list=None):
    parser = argparse.ArgumentParser(description="KnowledgeNet Code & Graph Assistant")
    parser.add_argument("--llmModel", default=None, help="LLM model")
    parser.add_argument("--llmApiEndpoint", default=None, help="LLM API endpoint")

    parser.add_argument("--embeddingApiUrl", default=None, help="Default URL for the embedding server (optional)")
    parser.add_argument("--embeddingModel", default='msmarco-MiniLM-L6-v3', help="Default embedding model (default: msmarco-MiniLM-L6-v3)")
    parser.add_argument("--embeddingProvider", default='huggingface', choices=['openai', 'huggingface'], help="Default embedding provider (default: huggingface)")
    parser.add_argument("--embeddings", nargs='+', default=[None], help='Embeddings used for this application. Accepts one or more values. Each value is of the format: <embedding_id>:[embedding_url][|][embedding_model][|][k][|][score_threshold][|][embedding_id]')

    parser.add_argument("--chromaHost", default='localhost', help="ChromaDB host (default: localhost)")
    parser.add_argument("--chromaPort", type=int, default=8000, help="ChromaDB port (default: 8000)")
    parser.add_argument("--baseCollections", nargs='+', default=['all_collection'], help='Base collection names (default: all_collection). Accepts one or more values. Each value is of the format: <collection_name>[|][search_algorithm][|][k][|][score_threshold]')
    parser.add_argument("--searchAlgorithm", type=str, default="similarity", help="Default search algorithm for retriever (e.g., 'similarity', 'mmr', etc.)")
    parser.add_argument("--scoreThreshold", type=float, default=None, help="Default score threshold for similarity_score_threshold search (optional)")
    parser.add_argument("--k", type=int, default=None, help="Default k (nearest neighbor) value")


    parser.add_argument("--format", choices=["raw", "structured"], default="structured", help="Output format: 'raw' or 'structured' (default: structured)")

    parser.add_argument("--contextPaths", nargs="+", default=[], help="List of file/folder paths for additional context")
    parser.add_argument("--contextPathsEmbedding", default='default', help="Embedding id to use for files in the contextPaths")

    parser.add_argument("--ensembleWeights", nargs=2, type=float, default=[], help="Weights for ensemble retriever (default: [])")
    
    parser.add_argument("--neo4jUri", type=str, default="bolt://localhost:7687", help="Neo4j connection URI.")
    parser.add_argument("--neo4jUser", type=str, default="neo4j", help="Neo4j username.")
    parser.add_argument("--neo4jPassword", type=str, default="password", help="Neo4j password.")
    parser.add_argument("--neo4jDatabase", type=str, default="neo4j", help="Neo4j database name (default: neo4j)")
    parser.add_argument("--graphLlmModel", default=None, type=str, help="Graph LLM model (langchain convention).")
    parser.add_argument("--graphLlmApiEndpoint", default=None, type=str, help="Graph LLM API endpoint.")
    parser.add_argument("--useGraphRag", action="store_true", help="Enable graph RAG chain (default: False)")
    parser.add_argument("--verbose", action="store_true", help="Enable verbose output from rag chain.")

    parser.add_argument("--log", default="INFO", choices=["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"], help="Set log level (default: INFO)")
   
    parser.add_argument("--promptDir", default=os.path.join(os.path.expanduser("~"), ".knowledgexpert", "conf", "expert"), help="Directory containing prompt templates (default: ~/.knowledgexpert/conf/expert)")

    parser.add_argument("--interactions", default=None, help="A string that is used to pass on additional interaction details (default: '')")

    parser.add_argument("--disableHistory", action="store_true", help="Disable message history for the assistant (default: False)")

    parser.add_argument("--confDir", default=None, help="Directory containing config.json for base configuration (optional)")

    parser.add_argument("--structureClass", default="knowledgexpert.structures.CodingAdvice", help="Fully qualified class name for structure (default: knowledgexpert.structures.CodingAdvice)")

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

    return args

if __name__ == "__main__":
    args = parse_args()

    base_config = {}
    if args.confDir:
        config_path = os.path.join(args.confDir, "config.json")
        with open(config_path, "r") as f:
            base_config = json.load(f)
            base_config = resolve_env_vars(base_config)
            delattr(args, "confDir")
           
    structure_class_path = args.structureClass
    delattr(args, "structureClass")

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
    logger.info("Initializing Knowledgexpert using parameters: %s", merged_config)

    module_name, class_name = structure_class_path.rsplit('.', 1)
    structure_module = importlib.import_module(module_name)
    structure_class = getattr(structure_module, class_name)
    expert = Expert(logger, structure=structure_class, **merged_config)
    serve_cli(expert, args.interactions)
