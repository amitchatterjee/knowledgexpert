import argparse
import chromadb

from langchain_chroma import Chroma
from langchain_huggingface import HuggingFaceEmbeddings
from langchain_community.document_loaders import TextLoader, DirectoryLoader
from langchain_text_splitters import TokenTextSplitter, PythonCodeTextSplitter, MarkdownTextSplitter
from langchain_community.embeddings import HuggingFaceInferenceAPIEmbeddings
from knowledgexpert.chunker import create_chunks

def parse_args():
    parser = argparse.ArgumentParser(description="Knowledge Store Builder")
    parser.add_argument("--documents", nargs='+', type=str, help="List of documents to process. This arg must be in the format: dir_path;key1:val1,key2:val2,... The system will process all files of type - python and md located under the directory specified by dir_path", default=[])
    parser.add_argument("--chunkSize", type=int, default=2000, help="Chunk size for splitters (tokens)")
    parser.add_argument("--chunkOverlap", type=int, default=200, help="Chunk overlap for splitters (tokens)")
    parser.add_argument("--log", type=str, default="INFO", help="Log severity level (DEBUG, INFO, WARNING, ERROR, CRITICAL)")
    parser.add_argument("--collectionName", type=str, default="all_collection", help="ChromaDB collection name")
    parser.add_argument("--chromaHost", type=str, default="localhost", help="ChromaDB host")
    parser.add_argument("--chromaPort", type=int, default=8000, help="ChromaDB port")
    parser.add_argument("--embeddingModel", type=str, default="msmarco-MiniLM-L6-v3", help="Embedding model name")
    parser.add_argument("--embeddingApiUrl", type=str, default=None, help="Remote HuggingFace Inference API endpoint URL (optional)")
    parser.add_argument("--clear", action="store_true", help="Purge the collection before adding new documents")
    parser.add_argument("--print", action="store_true", help="Print each chunk's source, metadata, and content")
    parser.add_argument("--store", action="store_true", help="Store the chunks in the vector store")
    return parser.parse_args()

def main(args):
    all_docs = []
    for document_spec in args.documents:
        dir_path, glob_pattern, *metadata_parts = document_spec.split(';')
        metadata = {}
        if not glob_pattern:
            glob = ["**/*.py", "**/*.md"]
        else:
            glob = glob_pattern.split(',')
        if metadata_parts:
            for item in metadata_parts[0].split(','):
                if item:
                    key, val = item.split(':', 1)
                    metadata[key.strip()] = val.strip()
        logger.debug('Loading documents from: {%s} with attributes: {%s}', dir_path, metadata )
        loader = DirectoryLoader(
            dir_path,
            glob=glob,
            loader_cls=TextLoader,
            recursive=True
        )
        docs = loader.load()
        logger.debug("Loaded %d document", len(docs))
        all_docs.append((docs, metadata))
   
    logger.info("Chunking documents...")
    py_splitter = PythonCodeTextSplitter(chunk_size=args.chunkSize, chunk_overlap=args.chunkOverlap)
    md_splitter = MarkdownTextSplitter(chunk_size=args.chunkSize, chunk_overlap=args.chunkOverlap)
    txt_splitter = TokenTextSplitter(chunk_size=args.chunkSize, chunk_overlap=args.chunkOverlap)
    doc_chunks = []
    for each in all_docs:
        chunk = create_chunks(each, py_splitter=py_splitter, md_splitter=md_splitter, txt_splitter=txt_splitter)
        # Add chunk_index to each chunk's metadata
        for idx, doc_chunk in enumerate(chunk):
            if not hasattr(doc_chunk, 'metadata'):
                doc_chunk.metadata = {}
            doc_chunk.metadata['chunk_index'] = idx
        if args.print:
            print_chunk_info(chunk)
        doc_chunks.extend(chunk)
    if args.store:
        chroma_client = chromadb.HttpClient(host=args.chromaHost, port=args.chromaPort)
        if args.clear:
            logger.info("Purging old values from store...")
            if args.collectionName in [col.name for col in chroma_client.list_collections()]:
                chroma_client.delete_collection(args.collectionName)
        # Support remote HuggingFace endpoint if embeddingApiUrl is provided
        embedding_function = None
        embedding_api_url = getattr(args, 'embeddingApiUrl', None)
        if embedding_api_url:
            embedding_function = HuggingFaceInferenceAPIEmbeddings(
                api_url=embedding_api_url,
                model_name=args.embeddingModel,
                api_key=""
            )
        else:
            embedding_function = HuggingFaceEmbeddings(model_name=args.embeddingModel)
        
        vector_store = Chroma(
            client=chroma_client,
            collection_name=args.collectionName,
            embedding_function=embedding_function
        )
        logger.info("Storing newly-found document chunks...")
        ids = []
        batch_size = 5
        for i in range(0, len(doc_chunks), batch_size):
            batch = doc_chunks[i:i+batch_size]
            batch_ids = vector_store.add_documents(documents=batch)
            ids.extend(batch_ids)
        logger.info(f"Stored {len(ids)} chunks in collection '{args.collectionName}'.")

def print_chunk_info(chunk):
    for doc_chunk in chunk:
        print(f"Source: {doc_chunk.metadata.get('source', '')}")
        print(f"Metadata: {doc_chunk.metadata}")
        print(f"Content:\n{getattr(doc_chunk, 'page_content', '')}\n{'-'*60}")

if __name__ == "__main__":
    import logging
    args = parse_args()
    logging.basicConfig(
        level=getattr(logging, args.log.upper(), logging.INFO),
        format='%(asctime)s %(levelname)s %(name)s: %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    logger = logging.getLogger("vector_store")
    logger.info(f"Initializing Knowledge Store with parameters: {args}")
    main(args)