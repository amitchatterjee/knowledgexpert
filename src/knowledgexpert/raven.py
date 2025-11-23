from argparse import Namespace
import asyncio
import json
from logging import Logger
import logging
import os
from typing import Any
from anthropic import BaseModel
import httpx
from langchain_mcp_adapters.client import MultiServerMCPClient
from langchain.agents import create_agent
from langchain.agents.structured_output import ToolStrategy
from langchain.agents.middleware import dynamic_prompt, ModelRequest
from langchain.tools import tool
from langchain_mcp_adapters.interceptors import ToolCallInterceptor, MCPToolCallRequest
import chromadb
from langchain_chroma import Chroma
from langchain_classic.retrievers import EnsembleRetriever
from langchain_core.tools.retriever import create_retriever_tool
from langchain.agents.middleware import wrap_tool_call
from langchain.messages import ToolMessage

from knowledgexpert.util import setup_llm
from knowledgexpert.util import setup_embedding, build_faiss_store_from_context

class Answer(BaseModel):
    summary: str
    answer: str
    reference: str


default_conf_dir = os.path.join(os.path.expanduser(
    "~"), ".knowledgexpert", "conf", "raven")

@dynamic_prompt
def raven_prompt(request: ModelRequest) -> str:
    raven_ctx: Raven = request.runtime.context.get("raven_ctx")
    prompt = str(raven_ctx.prompt)
    if not raven_ctx.args.skipRetrieval and raven_ctx.args.retrievalType == '2stepRag':
        prompt += f"""\n\n
        {raven_ctx.two_step_prompt}

        <contextual_information>
        Additional Contextual information
        {retrieve_from_vector_db(request, raven_ctx)} 
        </contextual_information>
        """
        
    if 'document' in request.runtime.context: 
        prompt += f"""\n\n{request.runtime.context['document']} 
    """
    
    raven_ctx.logger.debug("prompt: %s", prompt)
    return prompt

def retrieve_from_vector_db(request, raven_ctx):
    try:
        documents = raven_ctx.retriever.invoke(request.messages[0].content)
    except Exception as e:
        raven_ctx.logger.exception("Retriever invocation failed. %s", e)
        return f"Error retrieving documents: {e}"

    parts = []
    for i, doc in enumerate(documents):
        page = getattr(doc, "page_content", None) or ""
        meta = getattr(doc, "metadata", None) or {}
        parts.append(f"Source {i}:\n{page}\nMetadata: {meta}")
    retriever_context = "\n\n".join(parts) if parts else ""
    return retriever_context

@wrap_tool_call
def tool_wrapper(request, handler):
    """Debug logs tool execution traces and logs exception from a tool"""
    raven_ctx: Raven = request.runtime.context.get("raven_ctx")
    try:
        raven_ctx.logger.debug('Invoking tool %s, id: %s', request.tool.name, request.tool_call["id"])
        result = handler(request)
        raven_ctx.logger.debug('Invoked tool %s, id: %s, result: %s', request.tool.name, request.tool_call["id"], result)
        return result
    except Exception as e:
        raven_ctx.logger.exception(
            "Tool %s (id: %s) failed: %s",
            getattr(request.tool, "name", "<unknown>"),
            request.tool_call.get("id"),
            e,
        )
        return ToolMessage(
            content=f"Tool error: Please check your input and try again. ({str(e)})",
            tool_call_id=request.tool_call["id"])

class Raven:
    def __init__(self, logger: Logger, structure: Any = None, **kwargs):
        self.args = Namespace(**kwargs)
        self.logger = logger
        self.structure = structure
        self.prompt_dir = self.args.promptDir

        logging.getLogger("langchain").setLevel(self.logger.level)
        # Suppress HTTP request/response messages
        logging.getLogger("httpx").setLevel(logging.WARNING)
        logging.getLogger("urllib3").setLevel(logging.WARNING)
        logging.getLogger("requests").setLevel(logging.WARNING)
        # Suppress telemetry messages
        logging.getLogger("langchain.telemetry").setLevel(logging.WARNING)
        logging.getLogger("langchain_community.telemetry").setLevel(
            logging.WARNING)

        model = setup_llm(llm_model=self.args.llmModel,
                          llm_api_endpoint=self.args.llmApiEndpoint,
                          output_format=self.args.format,)

        tools = []
        if not self.args.skipMcpTools:
            tools.extend(asyncio.run(self._setup_mcp_tools(
                self.args.mcpConfig, insecure=self.args.mcpInsecure)))

        if not self.args.skipRetrieval:
            self.retriever = self._setup_vector_stores(self.args.chromaHost, self.args.chromaPort, self.args.baseCollections, self.args.ensembleWeights, self.args.contextPaths, self.args.contextPathsEmbedding, self.args.embeddings)
            if self.args.retrievalType == 'agenticRag':
                retriever_tool = create_retriever_tool(self.retriever,
                                                       name=self.args.vectorToolName,
                                                       description=self.args.vectorToolDescription)
                tools.append(retriever_tool)
            elif self.args.retrievalType == '2stepRag':
                self.two_step_prompt = self._setup_2step_rag_prompt(self.prompt_dir)

        self.prompt = self._setup_agentic_prompt(self.prompt_dir)

        self.agent = create_agent(
            model=model,
            tools=tools,
            middleware=[tool_wrapper, raven_prompt],
            response_format=ToolStrategy(self.structure))

    def _setup_2step_rag_prompt(self, prompt_dir):
        prompt_path = os.path.join(prompt_dir, "2step_rag_prompt.txt")
        prompt = "To answer the question, you can use the contextual information snippets are provided below."
        if os.path.exists(prompt_path):
            with open(prompt_path, "r", encoding="utf-8") as pf:
                prompt = pf.read()
        return prompt

    def _setup_agentic_prompt(self, prompt_dir):
        prompt_path = os.path.join(prompt_dir, "agentic_prompt.txt")
        prompt = "You are a helpful assistant. Be concise and accurate."
        if os.path.exists(prompt_path):
            with open(prompt_path, "r", encoding="utf-8") as pf:
                prompt = pf.read()
        else:
            self.logger.warning(
                "Agentic prompt file not found: %s", prompt_path)
        return prompt

    async def _setup_mcp_tools(self, mcp_config, insecure: bool = False):
        path = os.path.expanduser(mcp_config)
        verify = False if insecure else True
        if not verify:
            self.logger.warning(
                "TLS verification is disabled for MCP connections. This is insecure and should only be used for self-signed certificates.")

        def httpx_client_factory(headers: dict[str, str] | None = None, timeout: httpx.Timeout | None = None, auth: httpx.Auth | None = None) -> httpx.AsyncClient:
            client_headers = headers.copy() if headers else {}
            return httpx.AsyncClient(verify=verify, headers=client_headers, timeout=timeout, auth=auth)

        with open(path, "r", encoding="utf-8") as f:
            config = json.load(f)

        for v in config.values():
            if v.get("transport") in ("streamable_http", "sse"):
                v["httpx_client_factory"] = httpx_client_factory

        client = MultiServerMCPClient(config)
        tools = await client.get_tools()
        # Some MCP-provided tools are StructuredTool instances that only
        # implement an async coroutine (they have `coroutine` but no
        # synchronous `func`). Langchain's tooling may attempt to call
        # tools synchronously (for threaded execution) which raises
        # "StructuredTool does not support sync invocation." To support
        # those sync call-sites, provide a thin synchronous wrapper that
        # runs the coroutine in a fresh event loop when invoked.
        for t in tools:
            # Only wrap tools that expose a coroutine but no sync func
            try:
                has_coroutine = getattr(t, "coroutine", None) is not None
                has_func = getattr(t, "func", None) is not None
            except Exception:
                has_coroutine = False
                has_func = False
            if has_coroutine and not has_func:
                coro = t.coroutine

                def _make_sync(coro_fn):
                    def _sync_wrapper(*args, **kwargs):
                        return asyncio.run(coro_fn(*args, **kwargs))

                    return _sync_wrapper

                t.func = _make_sync(coro)
        self.logger.debug(
            "Loaded tools based on configuration file: %s", mcp_config)
        return tools

    def _setup_vector_stores(self, chroma_host, chroma_port, base_collections, ensemble_weights, context_paths, context_paths_embedding, embeddings):
        embeddings_dict = {}
        for embedding in embeddings:
            embeddings_dict[embedding['embeddingId']
                            ] = setup_embedding(embedding)

        faiss_store = None
        if context_paths:
            faiss_store = build_faiss_store_from_context(
                context_paths, embeddings_dict[context_paths_embedding])

        chroma_client = chromadb.HttpClient(host=chroma_host, port=chroma_port)
        retrievers = []
        weights = []
        for i, collection_element in enumerate(base_collections):
            vectorDb_kwargs = {"search_kwargs": {}}
            if 'k' in collection_element and collection_element['k']:
                vectorDb_kwargs["search_kwargs"]["k"] = collection_element['k']
            if 'searchAlgorithm' in collection_element and collection_element['searchAlgorithm'] == "similarity_score_threshold" and 'scoreThreshold' in collection_element and collection_element['scoreThreshold']:
                vectorDb_kwargs["search_kwargs"]["score_threshold"] = collection_element['scoreThreshold']

            vector_db = Chroma(
                client=chroma_client, collection_name=collection_element['collectionName'],
                embedding_function=embeddings_dict[collection_element['embeddingId']])
            retrievers.append(vector_db.as_retriever(
                search_type=collection_element['searchAlgorithm'], **vectorDb_kwargs))
            # Use ensemble_weights[i] if available, else default to 1.0
            if ensemble_weights and i < len(ensemble_weights):
                weights.append(ensemble_weights[i])
            else:
                weights.append(1.0)
        # Optionally add faiss_store as another retriever
        if faiss_store:
            retrievers.append(faiss_store.as_retriever())
            # If ensemble_weights has an extra value, use it, else default to 1.0
            if ensemble_weights and len(ensemble_weights) > len(base_collections):
                weights.append(ensemble_weights[len(base_collections)])
            else:
                weights.append(1.0)
        # If only one retriever, return it directly
        if len(retrievers) == 1:
            return retrievers[0]
        # Otherwise, return an ensemble retriever
        return EnsembleRetriever(retrievers=retrievers, weights=weights)

    def invoke(self, input: dict, context: dict = {}):
        context["raven_ctx"] = self
        response = self.agent.invoke(input, context=context)
        self.logger.debug("Response from agent:\n%s", response)
        return response['structured_response'] if 'structured_response' in response else response
