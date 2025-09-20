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

from knowledgexpert.util import setup_embedding
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
        self.embeddings_dict = {}

        logging.getLogger("langchain").setLevel(self.logger.level)
        # Suppress HTTP request/response messages
        logging.getLogger("httpx").setLevel(logging.WARNING)
        logging.getLogger("urllib3").setLevel(logging.WARNING)
        logging.getLogger("requests").setLevel(logging.WARNING)
        # Suppress telemetry messages
        logging.getLogger("langchain.telemetry").setLevel(logging.WARNING)
        logging.getLogger("langchain_community.telemetry").setLevel(logging.WARNING)

        for embedding in self.args.embeddings:
            self.embeddings_dict[embedding['embeddingId']] = setup_embedding(embedding)
            
        self.graph_chain = self._setup_graph_chain(
            self.args.useGraphRag, self.args.neo4jUri, self.args.neo4jUser, self.args.neo4jPassword, self.args.neo4jDatabase, self.args.graphLlmModel, self.args.graphLlmApiEndpoint, self.args.verbose)

        self.rag_chain = self._setup_vector_chain(self.args.chromaHost, self.args.chromaPort, self.args.baseCollections, self.args.ensembleWeights, self.args.contextPaths, self.args.contextPathsEmbedding, self.args.llmModel, self.args.llmApiEndpoint, self.args.format)

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

    def _setup_vector_stores(self, chroma_host, chroma_port, base_collections, ensemble_weights, context_paths, context_paths_embedding, embeddings_dict):
        faiss_store = None
        if context_paths:
            faiss_store = build_faiss_store_from_context(context_paths, embeddings_dict[context_paths_embedding])
        
        chroma_client = chromadb.HttpClient(host=chroma_host, port=chroma_port)
        retrievers = []
        weights = []
        for i, collection_element in enumerate(base_collections):
            vectorDb_kwargs = {"search_kwargs": {}}
            if 'k' in collection_element and collection_element['k']:
                vectorDb_kwargs["search_kwargs"]["k"] = collection_element['k']
            if 'searchAlgorithm' in collection_element and collection_element['searchAlgorithm'] == "similarity_score_threshold" and 'scoreThreshold' in collection_element and collection_element['scoreThreshold']:
                vectorDb_kwargs["search_kwargs"]["score_threshold"] = collection_element['scoreThreshold']
                
            vectorDb = Chroma(
                client=chroma_client, collection_name=collection_element['collectionName'], 
                embedding_function=embeddings_dict[collection_element['embeddingId']])
            retrievers.append(vectorDb.as_retriever(search_type=collection_element['searchAlgorithm'], **vectorDb_kwargs))
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

    def _setup_graph_chain(self, useGraphRag, neo4jUri, neo4jUser, neo4jPassword, neo4jDatabase, graphLlmModel, graphLlmApiEndpoint, verbose):
        if not useGraphRag:
            return None
        graph = Neo4jGraph(url=neo4jUri, username=neo4jUser, password=neo4jPassword, database=neo4jDatabase)
        graph_prompt_path = os.path.join(self.prompt_dir, "graph_prompt.txt")
        with open(graph_prompt_path, "r", encoding="utf-8") as f:
            system_prompt_text = f.read()
        system_prompt = SystemMessagePromptTemplate.from_template(system_prompt_text)
        human_prompt = HumanMessagePromptTemplate.from_template("{query}")
        chat_prompt = ChatPromptTemplate.from_messages([system_prompt, human_prompt])
        graph_llm = init_chat_model(graphLlmModel, base_url=graphLlmApiEndpoint)
        return GraphCypherQAChain.from_llm(graph_llm, graph=graph, verbose=verbose, allow_dangerous_requests=True, prompt=chat_prompt)

    def _setup_vector_chain(self, chroma_host, chroma_port, base_collections, ensemble_weights, context_paths, context_paths_embedding, llm_model, llm_api_endpoint, format):
        # Setup base retriever
        base_retriever = self._setup_vector_stores(
            chroma_host=chroma_host,
            chroma_port=chroma_port,
            base_collections=base_collections,
            ensemble_weights=ensemble_weights,
            context_paths=context_paths,
            context_paths_embedding=context_paths_embedding,
            embeddings_dict=self.embeddings_dict
        )

        llm = setup_llm(llm_model=llm_model,
                        llm_api_endpoint=llm_api_endpoint, output_format=format)

        llm_prompt_path = os.path.join(self.prompt_dir, "vector_prompt.txt")
        with open(llm_prompt_path, "r", encoding="utf-8") as f:
            llm_prompt_text = f.read()
        prompt = PromptTemplate(template=llm_prompt_text)

        def coding_advice_to_json(obj):
            return obj.model_dump_json()

        structured_llm = None
        if format == "structured":
            structured_llm = llm.with_structured_output(self.structure)
        params = {
            "interactions": RunnableLambda(lambda x: x["interactions"] if "interactions" in x else "None"),
            "graph_context": RunnableLambda(lambda x: x["graph_context"] if "graph_context" in x else "None"),
            "context": RunnableLambda(lambda x: x["input"]) | base_retriever | self._format_docs,
            "input": RunnableLambda(lambda x: x["input"]),
            "history": lambda x: x.get("history", []),
        }
        if structured_llm:
            params["schema"] = lambda x: self.structure.schema_json()
            rag_chain = (
                params
                | RunnableLambda(self._stop_if_no_context)
                | RunnableLambda(lambda x: (self.log_prompt(x), x)[1])
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

    def log_prompt(self, x):
        if self.args.verbose:
            self.logger.info("Input for vector llm: %s", x)
        return None

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
