from argparse import Namespace
import logging
from logging import Logger
import os
from typing import Any
import chromadb

import os

from langchain_chroma import Chroma
from langchain.chat_models.base import init_chat_model
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.runnables.history import RunnableWithMessageHistory
from langchain_core.runnables import RunnableLambda
from langchain_community.chat_message_histories import FileChatMessageHistory
from langchain_core.prompts import ChatPromptTemplate, PromptTemplate
from langchain_core.output_parsers import StrOutputParser

from langchain.retrievers import EnsembleRetriever
from langchain_community.graphs import Neo4jGraph
from langchain.chains import GraphCypherQAChain
from langchain_core.prompts import ChatPromptTemplate, SystemMessagePromptTemplate, HumanMessagePromptTemplate

from knowledgexpert.util import setup_embeddings
from knowledgexpert.util import setup_llm
from knowledgexpert.util import build_faiss_store_from_context

hist_dir = os.path.join(os.path.expanduser("~"), ".knowledgexpert", "history")
os.makedirs(hist_dir, exist_ok=True)

default_conf_dir = os.path.join(os.path.expanduser(
    "~"), ".knowledgexpert", "conf", "expert")

class Expert:
    def __init__(self, logger: Logger, structure:Any=None, **kwargs):       
        self.args = Namespace(**kwargs)
        self.logger = logger
        self.structure = structure
        self.prompt_dir = self.args.promptDir if self.args.promptDir else default_conf_dir

        logging.getLogger("langchain").setLevel(self.logger.level)
        # Suppress HTTP request/response messages
        logging.getLogger("httpx").setLevel(logging.WARNING)
        logging.getLogger("urllib3").setLevel(logging.WARNING)
        logging.getLogger("requests").setLevel(logging.WARNING)
        # Suppress telemetry messages
        logging.getLogger("langchain.telemetry").setLevel(logging.WARNING)
        logging.getLogger("langchain_community.telemetry").setLevel(logging.WARNING)

        self.embeddings = setup_embeddings(
            self.args.embeddingModel, self.args.embeddingApiUrl)

        self.graph_chain = self._setup_graph_chain(
            self.args.useGraphRag, self.args.neo4jUri, self.args.neo4jUser, self.args.neo4jPassword, self.args.graphLlmModel, self.args.graphLlmApiEndpoint, self.args.verbose)

        self.rag_chain = self._setup_vector_chain(self.args.chromaHost, self.args.chromaPort, self.args.baseCollection, self.args.searchAlgorithm,
                              self.args.scoreThreshold, self.args.ensembleWeights, self.args.k, self.args.contextPaths, self.args.llmModel, self.args.llmApiEndpoint, self.args.format)

        if getattr(self.args, "disableHistory", False):
            self.chat = self.rag_chain
        else:
            self.chat = RunnableWithMessageHistory(
                self.rag_chain, self._get_session_history, input_messages_key="input", history_messages_key="history")

    def _format_docs(self, docs):
        if not docs:
            return None
        context_str = "\n\n".join(doc.page_content for doc in docs)
        self.logger.debug("Retriever context:\n%s", context_str)
        return context_str

    def _stop_if_no_context(self, inputs):
        context = inputs["context"]
        if context is None or (isinstance(context, str) and not context.strip()):
            return {"output": "No relevant context found. Please try rephrasing your question."}
        return inputs

    def _get_session_history(self, session_id: str):
        file_path = os.path.join(hist_dir, f"history_{session_id}.json")
        return FileChatMessageHistory(file_path=file_path)

    def _setup_vector_stores(self, chromaHost, chromaPort, baseCollection, searchAlgorithm, scoreThreshold, ensembleWeights, k, context_paths, embeddings):
        faiss_store = build_faiss_store_from_context(context_paths, embeddings)
        chroma_client = chromadb.HttpClient(host=chromaHost, port=chromaPort)
        vectorDb_kwargs = {}
        if searchAlgorithm == "similarity_score_threshold" and scoreThreshold is not None:
            vectorDb_kwargs["search_kwargs"] = {
                "score_threshold": scoreThreshold,
                "k": k
            }
        else:
            vectorDb_kwargs["search_kwargs"] = {
                "k": k
            }
        vectorDb = Chroma(
            client=chroma_client, collection_name=baseCollection, embedding_function=embeddings)
        if faiss_store:
            retriever = EnsembleRetriever(
                retrievers=[vectorDb.as_retriever(
                    search_type=searchAlgorithm, **vectorDb_kwargs), faiss_store.as_retriever()],
                weights=ensembleWeights
            )
        else:
            retriever = vectorDb.as_retriever(
                search_type=searchAlgorithm, **vectorDb_kwargs)
        return retriever

    def _setup_graph_chain(self, useGraphRag, neo4jUri, neo4jUser, neo4jPassword, graphLlmModel, graphLlmApiEndpoint, verbose):
        if not useGraphRag:
            return None

        graph = Neo4jGraph(url=neo4jUri, username=neo4jUser,
                           password=neo4jPassword)
        graph_prompt_path = os.path.join(self.prompt_dir, "graph_prompt.txt")
        with open(graph_prompt_path, "r", encoding="utf-8") as f:
            system_prompt_text = f.read()

        system_prompt = SystemMessagePromptTemplate.from_template(
            system_prompt_text)
        human_prompt = HumanMessagePromptTemplate.from_template("{query}")
        chat_prompt = ChatPromptTemplate.from_messages(
            [system_prompt, human_prompt])
        graph_llm = init_chat_model(graphLlmModel, base_url=graphLlmApiEndpoint)
        return GraphCypherQAChain.from_llm(graph_llm, graph=graph, verbose=verbose, allow_dangerous_requests=True, prompt=chat_prompt)

    def _setup_vector_chain(self, chromaHost, chromaPort, baseCollection, searchAlgorithm, scoreThreshold, ensembleWeights, k, contextPaths, llmModel, llmApiEndpoint, format):
        retriever = self._setup_vector_stores(chromaHost=chromaHost, chromaPort=chromaPort, baseCollection=baseCollection, searchAlgorithm=searchAlgorithm,
                                             scoreThreshold=scoreThreshold, ensembleWeights=ensembleWeights,
                                             k = k, 
                                             context_paths=contextPaths, embeddings=self.embeddings)

        llm = setup_llm(llmModel=llmModel,
                        llmApiEndpoint=llmApiEndpoint, output_format=format)

        llm_prompt_path = os.path.join(self.prompt_dir, "vector_prompt.txt")
        with open(llm_prompt_path, "r", encoding="utf-8") as f:
            llm_prompt_text = f.read()
        prompt = PromptTemplate(template=llm_prompt_text, input_variables=[
                                "context", "history", "input"])

        def coding_advice_to_json(obj):
            return obj.model_dump_json()

        structured_llm = None
        if format == "structured":
            structured_llm = llm.with_structured_output(self.structure)
        params = {
            "interactions": RunnableLambda(lambda x: x["interactions"] if "interactions" in x else "None"),
            "graph_context": RunnableLambda(lambda x: x["graph_context"] if "graph_context" in x else "None"),
            "context": RunnableLambda(lambda x: x["input"]) | retriever | self._format_docs,
            "input": RunnableLambda(lambda x: x["input"]),
            "history": lambda x: x.get("history", []),
        }
        if structured_llm:
            params["schema"] = lambda x: self.structure.schema_json()
            rag_chain = (
                params
                | RunnableLambda(self._stop_if_no_context)
                | (prompt | structured_llm)
                | RunnableLambda(coding_advice_to_json)
            )
        else:
            rag_chain = (
                params
                | RunnableLambda(self._stop_if_no_context)
                | (prompt | llm | StrOutputParser())
            )
        return rag_chain

    def handle_question(self, user_query, name, interactions=''):
        graph_context = ""
        if self.args.useGraphRag:
            self.logger.debug("Step 1: Querying Neo4j graph...")
            try:
                graph_response = self.graph_chain.invoke(
                    {"query": user_query, 
                     "interactions": interactions
                    })
                graph_context = graph_response.get("result", "")
                self.logger.debug("Graph result:\n%s", graph_context)
            except Exception as e:
                self.logger.error("Graph query failed: %s", e)
                graph_context = ""
        self.logger.debug(f"Step 2: Querying vector RAG with graph context: %s", graph_context)
        try:
            out = self.chat.invoke({
                "input": user_query, 
                "graph_context": graph_context, 
                "interactions": interactions}, 
                config={
                    "configurable": {"session_id": name}
                })
            if self.args.format == "structured":
                out = self.structure.model_validate_json(out)
        except ValueError as ve:
            self.logger.error(
                "Structured output parsing failed: %s. Showing raw output.", ve)
            return str(ve)
        except Exception as e:
            self.logger.error("Error during chain invocation: %s", e)
            return str(e)
        self.logger.debug("Vector query output: %s", out)
        return out
