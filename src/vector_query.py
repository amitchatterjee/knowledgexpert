import argparse
from knowledgexpert.util import embedding_mapper, setup_embedding
from knowledgexpert.vector_backend import VectorDbConfig, create_vector_store

def parse_args():
    parser = argparse.ArgumentParser(description="Knowledge Query REPL")
    parser.add_argument("--vectorDbProvider", default='chroma', choices=['chroma', 'opensearch'], help="Vector DB provider (default: chroma)")
    parser.add_argument("--vectorDbHost", type=str, default="localhost", help="Vector DB host")
    parser.add_argument("--vectorDbPort", type=int, default=8000, help="Vector DB port")
    parser.add_argument("--vectorDbUseSsl", action="store_true", help="Use TLS when connecting to the vector DB")
    parser.add_argument("--vectorDbUsername", default=None, help="Optional vector DB username")
    parser.add_argument("--vectorDbPassword", default=None, help="Optional vector DB password")
    parser.add_argument("--vectorDbIndexPrefix", default=None, help="Optional index/collection prefix")
    parser.add_argument("--collectionName", type=str, default="all_collection", help="Logical vector collection/index name")
    parser.add_argument("--embeddingModel", type=str, default="msmarco-MiniLM-L6-v3", help="Embedding model name")
    parser.add_argument("--embeddingApiUrl", type=str, default=None, help="Embedding provider API endpoint URL (optional)")
    parser.add_argument("--k", type=int, default=100, help="Number of nearest neighbors to retrieve")
    parser.add_argument("--embeddingProvider", default='ollama', choices=['openai', 'ollama'], help="Embedding provider (default: ollama)")
    parser.add_argument("--searchAlgorithm", type=str, default="similarity", help="Search algorithm to use (e.g., 'similarity', 'mmr', etc.)")
    parser.add_argument("--scoreThreshold", type=float, default=0.7, help="Score threshold for similarity_score_threshold search algorithm")
    return parser.parse_args()

def init_vector_store(args):
    vector_db_config = VectorDbConfig.from_mapping(vars(args))
    embedding_function = setup_embedding(embedding_mapper(None, args.embeddingProvider, args.embeddingApiUrl, args.embeddingModel))

    vector_store = create_vector_store(
        config=vector_db_config,
        collection_name=args.collectionName,
        embedding_function=embedding_function,
    )
    return vector_store

def run_repl(vector_store):
    print("Knowledge Query REPL. Type 'exit' to quit.")
    while True:
        query = input("\nEnter your query: ")
        if query.strip().lower() in {"exit", "quit"}:
            print("Goodbye!")
            break
        if not query.strip():
            continue
        if args.searchAlgorithm == "mmr":
            retrieved_docs = vector_store.max_marginal_relevance_search(query, k=args.k)
        elif args.searchAlgorithm == "similarity_score_threshold":
            scored_results = vector_store.similarity_search_with_score(query, k=args.k)
            # scored_results is a list of (doc, score)
            retrieved_docs = [doc for doc, score in scored_results if score >= args.scoreThreshold]
        elif args.searchAlgorithm == "similarity":
            retrieved_docs = vector_store.similarity_search(query, k=args.k)
        else:
            # Fallback to similarity_search
            retrieved_docs = vector_store.similarity_search(query, k=args.k)
            
        print("Retrieved Documents:")
        for doc in retrieved_docs:
            print("-" * 40)
            print(f"Document ID: {doc.id}")
            print(f"Document metadata: {doc.metadata}")
            print(doc.page_content)

if __name__ == "__main__":
    args = parse_args()
    print(
        "Initializing Knowledge Query with "
        f"{args.vectorDbProvider} at {args.vectorDbHost}:{args.vectorDbPort}, "
        f"using collection '{args.collectionName}' and embedding model '{args.embeddingModel}'"
    )
    vector_store = init_vector_store(args)
    run_repl(vector_store)

