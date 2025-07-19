import os
import argparse
from typing import Optional
import chromadb
import string
import logging

from rich.console import Console
from rich.markdown import Markdown
import os

from langchain_chroma import Chroma
from langchain.chat_models.base import init_chat_model
from langchain_huggingface import HuggingFaceEmbeddings
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_core.runnables.history import RunnableWithMessageHistory
from langchain_core.runnables import RunnablePassthrough, RunnableLambda
from langchain_community.chat_message_histories import FileChatMessageHistory
from langchain.output_parsers import PydanticOutputParser
from pydantic import BaseModel, Field
from langchain_core.prompts import ChatPromptTemplate, PromptTemplate
from langchain_core.output_parsers import StrOutputParser
from langchain_community.vectorstores import FAISS
from langchain_community.document_loaders import TextLoader
from langchain.text_splitter import RecursiveCharacterTextSplitter
from langchain.retrievers import EnsembleRetriever
from langchain_community.graphs import Neo4jGraph
from langchain.chains import GraphCypherQAChain
from langchain_core.prompts import ChatPromptTemplate, SystemMessagePromptTemplate, HumanMessagePromptTemplate
from langchain_community.embeddings import HuggingFaceInferenceAPIEmbeddings

# NOTE the API_KEY environment variable specific to LLM/Embedding provider must be set for this application to work

hist_dir = os.path.join(os.path.expanduser("~"), ".knowledgexpert/history")
os.makedirs(hist_dir, exist_ok=True)

class CodingAdvice(BaseModel):
    summary: Optional[str] = Field("A one-line summary of the code snippet")
    description: Optional[str] = Field(description = "Description of the code snippet")
    code: str = Field(description="A Python Code Snippet")
    explanation: Optional[str] = Field(description="Detailed explaination of the code")
    references: Optional[list] = Field(description = "A list of URLs containing more information")

def format_docs(docs):
    if not docs:
        return None
    return "\n\n".join(doc.page_content for doc in docs)


def stop_if_no_context(inputs):
    # If context is None or empty, return a message and skip the rest of the chain
    context = inputs["context"]
    if context is None or (isinstance(context, str) and not context.strip()):
        # You can customize this message
        return {"output": "No relevant context found. Please try rephrasing your question."}
    return inputs

def get_session_history(session_id: str):
    # Each session gets its own file, e.g., "history_<session_id>.json"
    file_path = os.path.join(hist_dir, f"history_{session_id}.json")
    return FileChatMessageHistory(file_path=file_path)

def is_text_file(filepath, blocksize=512):
    try:
        with open(filepath, 'rb') as f:
            chunk = f.read(blocksize)
            if not chunk:
                return True  # Empty files are considered text
            # If there are null bytes, it's likely binary
            if b'\x00' in chunk:
                return False
            # Check if most bytes are printable (ASCII or UTF-8)
            text_characters = bytes(string.printable, 'ascii')
            nontext = [b for b in chunk if b not in text_characters]
            # Heuristic: if more than 30% non-printable, treat as binary
            return float(len(nontext)) / len(chunk) < 0.30
    except Exception:
        return False

def build_faiss_store_from_context(context_paths, embeddings):
    additional_context = []
    if context_paths:
        for path in context_paths:
            if os.path.isdir(path):
                for root, _, files in os.walk(path):
                    for file in files:
                        file_path = os.path.join(root, file)
                        if not is_text_file(file_path):
                            continue
                        try:
                            loader = TextLoader(file_path, encoding="utf-8", autodetect_encoding=True)
                            additional_context.extend(loader.load())
                        except Exception:
                            continue
            elif os.path.isfile(path):
                try:
                    loader = TextLoader(path, encoding="utf-8", autodetect_encoding=True)
                    additional_context.extend(loader.load())
                except Exception:
                    continue

    if additional_context:
        text_splitter = RecursiveCharacterTextSplitter(chunk_size=1000, chunk_overlap=100)
        docs = text_splitter.split_documents(additional_context)
        faiss_store = FAISS.from_documents(docs, embeddings)
        return faiss_store
    return None

def setup_embeddings(args):
    if args.embeddingApiUrl:
        # Use remote HuggingFace Inference API endpoint
        return HuggingFaceInferenceAPIEmbeddings(
            api_url=args.embeddingApiUrl,
            model_name=args.embeddingModel,
            api_key=""
        )
    else:
        # Use local HuggingFace model
        return HuggingFaceEmbeddings(model_name=args.embeddingModel)

def setup_vector_store(args, embeddings):
    faiss_store = build_faiss_store_from_context(args.contextPaths, embeddings)
    chroma_client = chromadb.HttpClient(host=args.chromaHost, port=args.chromaPort)
    vectorDb_kwargs = {}
    # Only apply score threshold if using similarity_score_threshold
    if args.searchAlgorithm == "similarity_score_threshold" and args.scoreThreshold is not None:
        vectorDb_kwargs["search_kwargs"] = {"score_threshold": args.scoreThreshold}
    vectorDb = Chroma(
        client=chroma_client,
        collection_name=args.baseCollection,
        embedding_function=embeddings
    )
    # Use searchAlgorithm for retriever
    if faiss_store:
        retriever = EnsembleRetriever(
            retrievers=[vectorDb.as_retriever(search_type=args.searchAlgorithm, **vectorDb_kwargs), faiss_store.as_retriever()],
            weights=args.ensembleWeights
        )
    else:
        retriever = vectorDb.as_retriever(search_type=args.searchAlgorithm, **vectorDb_kwargs)
    return retriever

def setup_llm(args):
    model_provider = args.llmModel.split(":")[0]
    if model_provider == 'openai' or model_provider == 'ollama':
        return init_chat_model(
            args.llmModel,
            base_url=args.llmApiEndpoint,
            temperature=0,
            streaming=True,
            model_kwargs={"response_format": {"type": "json_object"}} if args.format == "structured" else {}
        )
    else:
        return init_chat_model(
            args.llmModel,
            base_url=args.llmApiEndpoint,
            temperature=0,
            streaming=True
        )

def setup_graph_chain(args):
    graph = Neo4jGraph(
        url=args.neo4jUri,
        username=args.neo4jUser,
        password=args.neo4jPassword
    )
    system_prompt = SystemMessagePromptTemplate.from_template(
        "You are a helpful assistant for querying a Neo4j knowledge graph. "
        "The graph captures the relationship between python modules, classes, functions and attributes for an application. "
        "The nodes are named appropriately. "
        "Answer the user's graph-related questions clearly and concisely. "
        "If the question is unrelated to the graph, don't attempt to create the query"
    )
    human_prompt = HumanMessagePromptTemplate.from_template("{query}")
    chat_prompt = ChatPromptTemplate.from_messages([system_prompt, human_prompt])
    graph_llm = init_chat_model(args.graphLlmModel, base_url=args.graphLlmApiEndpoint)
    return GraphCypherQAChain.from_llm(
        graph_llm,
        graph=graph,
        verbose=args.verbose,
        allow_dangerous_requests=True,
        prompt=chat_prompt
    )

def setup_vector_chain(args, retriever, llm):
    prompt = PromptTemplate(
        template=(
        "You are a helpful code assistant. First, use the following context to answer the user's question. "
        "If you are generating code, please include the necessary imports. "
        "If the graph context is insufficient, use the additional vector context.\n\n"
        "Graph Context:\n{graph_context}\n\n"
        "Context: \n{context}\n\n"
        "History:\n{history}\n"
        "User: {input}\n"
        ),
        input_variables=["context", "history", "input"]
    )
    def coding_advice_to_json(obj):
        return obj.model_dump_json()
    
    structured_llm = None
    if args.format == "structured":
        structured_llm = llm.with_structured_output(CodingAdvice)
    if structured_llm:
        rag_chain = (
            {
                "graph_context": RunnableLambda(lambda x: x["graph_context"]),
                "context": RunnableLambda(lambda x: x["input"]) | retriever | format_docs,
                "input": RunnableLambda(lambda x: x["input"]),
                "history": lambda x: x.get("history", []),
            }
            | RunnableLambda(stop_if_no_context)
            | (prompt | structured_llm)
            | RunnableLambda(coding_advice_to_json)
        )
    else:
        rag_chain = (
            {
                "graph_context": RunnableLambda(lambda x: x["graph_context"]),
                "context": RunnableLambda(lambda x: x["input"]) | retriever | format_docs,
                "input": RunnableLambda(lambda x: x["input"]),
                "history": lambda x: x.get("history", []),
            }
            | RunnableLambda(stop_if_no_context)
            | (prompt | llm | StrOutputParser())
        )
    return rag_chain

def init(args, parent_logger):
    global embeddings, retriever, llm, rag_chain, chat_with_history, graph_chain, logger
    logger = parent_logger
    
    embeddings = setup_embeddings(args)
    retriever = setup_vector_store(args, embeddings)
    llm = setup_llm(args)
    graph_chain = setup_graph_chain(args)
    rag_chain = setup_vector_chain(args, retriever, llm)
    chat_with_history = RunnableWithMessageHistory(
        rag_chain,
        get_session_history,
        input_messages_key="input",
        history_messages_key="history",
    )

def parse_args(args_list=None):
    parser = argparse.ArgumentParser(description="KnowledgeNet Code & Graph Assistant")
    # Vector RAG options
    parser.add_argument("--llmModel", default='openai:deepseek-r1-671b', help="LLM model (default: openai:deepseek-r1-671b)")
    parser.add_argument("--llmApiEndpoint", default='https://api.lambda.ai/v1', help="LLM API endpoint (default: https://api.lambda.ai/v1)")
    parser.add_argument("--embeddingModel", default='msmarco-MiniLM-L-6-v3', help="Embedding model (default: msmarco-MiniLM-L-6-v3)")
    parser.add_argument("--chromaHost", default='localhost', help="ChromaDB host (default: localhost)")
    parser.add_argument("--chromaPort", type=int, default=8000, help="ChromaDB port (default: 8000)")
    parser.add_argument("--baseCollection", default='rules_collection', help="Base collection name (default: rules_collection)")
    parser.add_argument("--searchAlgorithm", type=str, default="similarity", help="Search algorithm for retriever (e.g., 'similarity', 'mmr', etc.)")
    parser.add_argument("--scoreThreshold", type=float, default=None, help="Score threshold for similarity_score_threshold search (optional)")
    parser.add_argument("--format", choices=["raw", "structured"], default="structured", help="Output format: 'raw' or 'structured' (default: structured)")
    parser.add_argument("--contextPaths", nargs="+", default=[], help="List of file/folder paths for additional context")
    parser.add_argument("--embeddingApiUrl", default=None, help="URL of remote HuggingFace embedding server (optional)")
    # Graph RAG options
    parser.add_argument("--neo4jUri", type=str, default="bolt://localhost:7687", help="Neo4j connection URI.")
    parser.add_argument("--neo4jUser", type=str, default="neo4j", help="Neo4j username.")
    parser.add_argument("--neo4jPassword", type=str, default="password", help="Neo4j password.")
    parser.add_argument("--graphLlmModel", type=str, default="ollama:codellama:latest", help="Graph LLM model (langchain convention).")
    parser.add_argument("--graphLlmApiEndpoint", type=str, default="http://localhost:11434", help="Graph LLM API endpoint.")
    parser.add_argument("--useGraphRag", action="store_true", help="Enable graph RAG chain (default: False)")
    parser.add_argument("--verbose", action="store_true", help="Enable verbose output from gag chain.")
    parser.add_argument("--log", default="INFO", choices=["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"], help="Set log level (default: INFO)")
    parser.add_argument("--ensembleWeights", nargs=2, type=float, default=[0.5, 0.5], help="Weights for ensemble retriever (default: 0.5 0.5)")
    if args_list is not None:
        return parser.parse_args(args_list)
    else:
        return parser.parse_args()

def load_additional_context(paths):
    context_data = []
    for path in paths:
        if os.path.isdir(path):
            for root, _, files in os.walk(path):
                for file in files:
                    file_path = os.path.join(root, file)
                    with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
                        context_data.append({"path": file_path, "content": f.read()})
        elif os.path.isfile(path):
            with open(path, "r", encoding="utf-8", errors="ignore") as f:
                context_data.append({"path": path, "content": f.read()})
    return context_data

def handle_question(user_query, name, args):
    graph_context = ""
    if args.useGraphRag:
        logger.debug("Step 1: Querying Neo4j graph...")
        try:
            graph_response = graph_chain.invoke({"query": user_query})
            graph_context = graph_response.get("result", "")
            logger.debug("Graph result:\n%s", graph_context)
        except Exception as e:
            logger.error("Graph query failed: %s", e)
            graph_context = ""
    logger.debug("Step 2: Querying vector RAG with graph context...")
    try:
        out = chat_with_history.invoke({"input": user_query, "graph_context": graph_context}, config={"configurable": {"session_id": name}})
        if args.format == "structured":
            out = CodingAdvice.model_validate_json(out)
    except ValueError as ve:
        logger.error("Structured output parsing failed: %s. Showing raw output.", ve)
        return str(ve)
    except Exception as e:
        logger.error("Error during chain invocation: %s", e)
        return str(e)
    return out

def serve_cli(args):
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
        out = handle_question(user_query, name, args)
        console.print("Knowledge Assistant: Here is my response. I make mistakes. So, please double-check my answers.")
        if type(out) == CodingAdvice:
            print_structured_output(out, console)
        else:
            console.print(out)

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

if __name__ == "__main__":  
    args = parse_args()
    log_level = getattr(logging, args.log.upper(), logging.INFO)
    logging.basicConfig(level=log_level, format='%(asctime)s %(levelname)s %(message)s')
    logger = logging.getLogger('knowledgexpert')
    print("Note: If you are using a commercial LLM, make sure you have the necessary environment variable with the secret")
    logger.info("Initializing Knowledge Expert using parameters: %s", args)
    init(args, logger)
    serve_cli(args)
