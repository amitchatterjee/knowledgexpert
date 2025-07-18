import ast
import os
import argparse
import chromadb
from langchain_chroma import Chroma
from langchain_huggingface import HuggingFaceEmbeddings
from langchain_community.document_loaders import TextLoader, DirectoryLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_community.embeddings import HuggingFaceInferenceAPIEmbeddings


def split_python_code_by_function(code):
    """Split Python code into chunks by function and class definitions."""
    tree = ast.parse(code)
    chunks = []
    lines = code.splitlines()
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.ClassDef)):
            start = node.lineno - 1
            end = node.end_lineno
            chunk = '\n'.join(lines[start:end])
            chunks.append(chunk)
    return chunks

def parse_args():
    parser = argparse.ArgumentParser(description="Knowledge Store Builder")
    parser.add_argument("--documents", nargs='+', type=str, help="List of documents to process. This arg must be in the format: dir_path;key1:val1,key2:val2,... The system will process all files of type - python and md located under the directory specified by dir_path", default=[])
    parser.add_argument("--log", type=str, default="INFO", help="Log severity level (DEBUG, INFO, WARNING, ERROR, CRITICAL)")
    parser.add_argument("--collectionName", type=str, default="rules_collection", help="ChromaDB collection name")
    parser.add_argument("--chromaHost", type=str, default="localhost", help="ChromaDB host")
    parser.add_argument("--chromaPort", type=int, default=8000, help="ChromaDB port")
    parser.add_argument("--embeddingModel", type=str, default="all-MiniLM-L6-v2", help="Embedding model name")
    parser.add_argument("--embeddingApiUrl", type=str, default=None, help="Remote HuggingFace Inference API endpoint URL (optional)")
    parser.add_argument("--clear", action="store_true", help="Purge the collection before adding new documents")
    parser.add_argument("--print", action="store_true", help="Print each chunk's source, metadata, and content")
    parser.add_argument("--store", action="store_true", help="Store the chunks in the vector store")
    return parser.parse_args()

def main(args):
    all_docs = []
    for document_spec in args.documents:
        dir_path, *metadata_parts = document_spec.split(';')
        metadata = {}
        if metadata_parts:
            for item in metadata_parts[0].split(','):
                if item:
                    key, val = item.split(':', 1)
                    metadata[key.strip()] = val.strip()
        logger.debug('Loading documents from: {%s} with attributes: {%s}', dir_path, metadata )
        loader = DirectoryLoader(
            dir_path,
            glob=["**/*.py", "**/*.md"],
            loader_cls=TextLoader,
            recursive=True
        )
        docs = loader.load()
        logger.debug("Loaded %d document", len(docs))
        all_docs.append((docs, metadata))
   
    logger.info("Chunking documents...")
    splitter = RecursiveCharacterTextSplitter(chunk_size=500, chunk_overlap=50)
    doc_chunks = []
    for each in all_docs:
        chunk = create_chunks(each, splitter)
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
        batch_size = 32
        #doc_chunks = [chunk for chunk in doc_chunks if not chunk.metadata.get('source', '').endswith('.py')]
        for i in range(0, len(doc_chunks), batch_size):
            batch = doc_chunks[i:i+batch_size]
            batch_ids = vector_store.add_documents(documents=batch)
            ids.extend(batch_ids)
        logger.info(f"Stored {len(ids)} chunks in collection '{args.collectionName}'.")

def print_chunk_info(chunk):
    for doc_chunk in chunk:
        print(f"Source: {doc_chunk.metadata.get('source', '')}")
        print(f"Metadata: {doc_chunk.metadata}")
        print(f"Content:\n{doc_chunk.page_content}\n{'-'*60}")

def create_chunks(doc_tuple, splitter):
    doc_chunks = []
    for each in doc_tuple[0]:
        source = each.metadata.get('source', '')
        if source.endswith('.py'):
            # Extract import statements from the module header
            lines = each.page_content.splitlines()
            import_lines = [line for line in lines if line.strip().startswith(('import ', 'from '))]
            import_block = '\n'.join(import_lines) + '\n' if import_lines else ''
            for chunk in split_python_code_by_function(each.page_content):
                if isinstance(chunk, str) and chunk.strip():
                    # Use splitter to further split the function/class chunk
                    sub_chunks = splitter.split_text(chunk)
                    for sub_chunk in sub_chunks:
                        if isinstance(sub_chunk, str) and sub_chunk.strip():
                            chunk_with_imports = import_block + sub_chunk
                            doc_chunk = type(each)(page_content=chunk_with_imports, metadata=each.metadata)
                            doc_chunk.metadata.update({'type': 'code', 'language': 'python'})
                            doc_chunk.metadata.update(doc_tuple[1])
                            doc_chunks.append(doc_chunk)
        else:
            for chunk in splitter.split_documents([each]):
                if isinstance(chunk.page_content, str) and chunk.page_content.strip():
                    chunk.metadata.update(doc_tuple[1])
                    doc_chunks.append(chunk)
    return doc_chunks

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