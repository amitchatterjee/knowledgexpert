import os
import logging
from rich.console import Console
import argparse
from knowledgexpert.expert import Expert, CodingAdvice

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

def serve_cli(expert):
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
        out = expert.handle_question(user_query, name)
        console.print("Knowledge Assistant: Here is my response. I make mistakes. So, please double-check my answers.")
        if type(out) == CodingAdvice:
            print_structured_output(out, console)
        else:
            console.print(out)

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
    parser.add_argument("--promptDir", default=os.path.join(os.path.expanduser("~"), ".knowledgexpert", "conf", "expert"), help="Directory containing prompt templates (default: ~/.knowledgexpert/conf/expert)"
    )
    if args_list is not None:
        return parser.parse_args(args_list)
    else:
        return parser.parse_args()

if __name__ == "__main__":  
    args = parse_args()
    log_level = getattr(logging, args.log.upper(), logging.INFO)
    logging.basicConfig(level=log_level, format='%(asctime)s %(levelname)s %(message)s')
    logger = logging.getLogger('knowledgexpert')
    print("Note: If you are using a commercial LLM, make sure you have the necessary environment variable with the secret")
    logger.info("Initializing Knowledge Expert using parameters: %s", args)
    expert = Expert(args, logger)
    serve_cli(expert)
