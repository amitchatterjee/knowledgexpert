import argparse
import chromadb
from langchain_chroma import Chroma
from langchain_huggingface import HuggingFaceEmbeddings
from langchain_community.embeddings import HuggingFaceInferenceAPIEmbeddings

def parse_args():
    parser = argparse.ArgumentParser(description="Knowledge Query REPL")
    parser.add_argument("--chromaHost", type=str, default="localhost", help="ChromaDB host")
    parser.add_argument("--chromaPort", type=int, default=8000, help="ChromaDB port")
    parser.add_argument("--collectionName", type=str, default="rules_collection", help="ChromaDB collection name")
    parser.add_argument("--embeddingModel", type=str, default="all-MiniLM-L6-v2", help="Embedding model name")
    parser.add_argument("--embeddingApiUrl", type=str, default=None, help="Remote HuggingFace Inference API endpoint URL (optional)")
    parser.add_argument("--k", type=int, default=100, help="Number of nearest neighbors to retrieve")
    return parser.parse_args()

def init_vector_store(args):
    chroma_client = chromadb.HttpClient(host=args.chromaHost, port=args.chromaPort)
    embedding_function = None
    embedding_api_url = getattr(args, 'embeddingApiUrl', None)
    if embedding_api_url:
        embedding_function = HuggingFaceInferenceAPIEmbeddings(
            api_url=embedding_api_url,
            model_name=args.embeddingModel
        )
    else:
        embedding_function = HuggingFaceEmbeddings(model_name=args.embeddingModel)
    vector_store = Chroma(
        client=chroma_client,
        collection_name=args.collectionName,
        embedding_function=embedding_function
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
        retrieved_docs = vector_store.similarity_search(query, k=args.k)
        print("Retrieved Documents:")
        for doc in retrieved_docs:
            print(f"Document ID: {doc.id}")
            print(f"Document metadata: {doc.metadata}")
            print(doc.page_content)
        print("-" * 40)

if __name__ == "__main__":
    args = parse_args()
    print(f"Initializing Knowledge Query with ChromaDB at {args.chromaHost}:{args.chromaPort}, using collection '{args.collectionName}' and embedding model '{args.embeddingModel}'")
    vector_store = init_vector_store(args)
    run_repl(vector_store)

