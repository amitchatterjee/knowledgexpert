import argparse
import logging
import os
import sys

from knowledgexpert.raven import Answer, Raven
from knowledgexpert.util import embedding_mapper

def parse_args():
    parser = argparse.ArgumentParser(description="Raven CLI")

    # LLM-related stuff
    parser.add_argument("--llmModel", help="LLM model identifier")
    parser.add_argument("--llmApiEndpoint", default=None, help="LLM API endpoint")
    parser.add_argument("--promptDir", default=os.path.join(os.path.expanduser("~"), ".knowledgexpert", "conf", "raven"), help="Directory containing prompt templates (default: ~/.knowledgexpert/conf/prompt)")

    # Options
    parser.add_argument("--format", choices=["raw", "structured"], default="structured", help="Output format: 'raw' or 'structured'")
    parser.add_argument("--skipVectorRetrieval", action="store_true", help="Skip vector database retrieval and send the prompt directly to the LLM (default: False)")
    parser.add_argument("--vectorRetrievalType", choices=["2step", "agentic"], default="agentic", help="Specify what style of vector retrieval is needed. Default: 'agentic'") 
    parser.add_argument("--skipMcpTools", action="store_true", help="Skip MCP tools use and send the prompt directly to the LLM (default: False)")

    # Vector-related stuff
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
    parser.add_argument("--contextPaths", nargs="+", default=[], help="List of file/folder paths for additional context")
    parser.add_argument("--contextPathsEmbedding", default='default', help="Embedding id to use for files in the contextPaths")
    parser.add_argument("--ensembleWeights", nargs=2, type=float, default=[], help="Weights for ensemble retriever (default: [])")

    # MCP-related stuff
    parser.add_argument("--mcpConfig", required=True, help="Path to MCP config JSON")
    parser.add_argument("--mcpInsecure", action="store_true", help="Disable TLS verification for MCP")

    parser.add_argument("--input", required=True, help="Input text to invoke the agent with")

    args = parser.parse_args()
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

if __name__ == "__main__":
    args = parse_args()

    logger = logging.getLogger("Raven driver")
    logger.setLevel(logging.DEBUG)
    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter("%(levelname)s: %(message)s"))
    logger.addHandler(handler)

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
    
    merged_config = dict(vars(args))

    try:
        raven = Raven(logger,structure=Answer,**merged_config)
        input = {"messages": [{"role": "user", "content": args.input}]}
        result = raven.invoke(input)
        print("Agent result:")
        print(result)

    except Exception as e:
        logger.exception("Failed to run Raven: %s", e)
        sys.exit(1)
