import os
from typing import Optional
import chromadb
import string

import os

from langchain_chroma import Chroma
from langchain.chat_models.base import init_chat_model
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.runnables.history import RunnableWithMessageHistory
from langchain_core.runnables import RunnableLambda
from langchain_community.chat_message_histories import FileChatMessageHistory
from pydantic import BaseModel, Field
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

default_prompt_dir = os.path.join(os.path.expanduser(
    "~"), ".knowledgexpert", "conf", "expert")

class CodingAdvice(BaseModel):
    summary: Optional[str] = Field("A one-line summary of the code snippet")
    description: Optional[str] = Field(
        description="Description of the code snippet")
    code: str = Field(description="A Python Code Snippet")
    explanation: Optional[str] = Field(
        description="Detailed explaination of the code")
    references: Optional[list] = Field(
        description="A list of URLs containing more information")

class Expert:
    def __init__(self, args, logger):
        self.args = args
        self.logger = logger
        self.prompt_dir = args.promptDir if args.promptDir else default_prompt_dir
        
        self.embeddings = setup_embeddings(args.embeddingModel, args.embeddingApiUrl)
        self.retriever = self._setup_vector_store(
            chromaHost=args.chromaHost,
            chromaPort=args.chromaPort,
            baseCollection=args.baseCollection,
            searchAlgorithm=args.searchAlgorithm,
            scoreThreshold=args.scoreThreshold,
            ensembleWeights=args.ensembleWeights,
            context_paths=args.contextPaths,
            embeddings=self.embeddings
        )
        
        self.llm = setup_llm(
            llmModel=args.llmModel,
            llmApiEndpoint=args.llmApiEndpoint,
            output_format=args.format
        )
        self.graph_chain = self._setup_graph_chain()
        self.rag_chain = self._setup_vector_chain()
        self.chat_with_history = RunnableWithMessageHistory(
            self.rag_chain,
            self._get_session_history,
            input_messages_key="input",
            history_messages_key="history",
        )

    def _format_docs(self, docs):
        if not docs:
            return None
        return "\n\n".join(doc.page_content for doc in docs)

    def _stop_if_no_context(self, inputs):
        context = inputs["context"]
        if context is None or (isinstance(context, str) and not context.strip()):
            return {"output": "No relevant context found. Please try rephrasing your question."}
        return inputs

    def _get_session_history(self, session_id: str):
        file_path = os.path.join(hist_dir, f"history_{session_id}.json")
        return FileChatMessageHistory(file_path=file_path)


    def _setup_vector_store(self, chromaHost, chromaPort, baseCollection, searchAlgorithm, scoreThreshold, ensembleWeights, context_paths, embeddings):        
        faiss_store = build_faiss_store_from_context(context_paths, embeddings)
        chroma_client = chromadb.HttpClient(host=chromaHost, port=chromaPort)
        vectorDb_kwargs = {}
        if searchAlgorithm == "similarity_score_threshold" and scoreThreshold is not None:
            vectorDb_kwargs["search_kwargs"] = {
                "score_threshold": scoreThreshold}
        vectorDb = Chroma(
            client=chroma_client,
            collection_name=baseCollection,
            embedding_function=embeddings
        )
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


    def _setup_graph_chain(self):
        graph = Neo4jGraph(
            url=self.args.neo4jUri,
            username=self.args.neo4jUser,
            password=self.args.neo4jPassword
        )
        graph_prompt_path = os.path.join(self.prompt_dir, "graph_prompt.txt")
        with open(graph_prompt_path, "r", encoding="utf-8") as f:
            system_prompt_text = f.read()

        system_prompt = SystemMessagePromptTemplate.from_template(
            system_prompt_text)
        human_prompt = HumanMessagePromptTemplate.from_template("{query}")
        chat_prompt = ChatPromptTemplate.from_messages(
            [system_prompt, human_prompt])
        graph_llm = init_chat_model(
            self.args.graphLlmModel, base_url=self.args.graphLlmApiEndpoint)
        return GraphCypherQAChain.from_llm(
            graph_llm,
            graph=graph,
            verbose=self.args.verbose,
            allow_dangerous_requests=True,
            prompt=chat_prompt
        )

    def _setup_vector_chain(self):
        llm_prompt_path = os.path.join(self.prompt_dir, "llm_prompt.txt")
        with open(llm_prompt_path, "r", encoding="utf-8") as f:
            llm_prompt_text = f.read()
        prompt = PromptTemplate(
            template=llm_prompt_text,
            input_variables=["context", "history", "input"]
        )

        def coding_advice_to_json(obj):
            return obj.model_dump_json()

        structured_llm = None
        if self.args.format == "structured":
            structured_llm = self.llm.with_structured_output(CodingAdvice)
        if structured_llm:
            rag_chain = (
                {
                    "graph_context": RunnableLambda(lambda x: x["graph_context"]),
                    "context": RunnableLambda(lambda x: x["input"]) | self.retriever | self._format_docs,
                    "input": RunnableLambda(lambda x: x["input"]),
                    "history": lambda x: x.get("history", []),
                }
                | RunnableLambda(self._stop_if_no_context)
                | (prompt | structured_llm)
                | RunnableLambda(coding_advice_to_json)
            )
        else:
            rag_chain = (
                {
                    "graph_context": RunnableLambda(lambda x: x["graph_context"]),
                    "context": RunnableLambda(lambda x: x["input"]) | self.retriever | self._format_docs,
                    "input": RunnableLambda(lambda x: x["input"]),
                    "history": lambda x: x.get("history", []),
                }
                | RunnableLambda(self._stop_if_no_context)
                | (prompt | self.llm | StrOutputParser())
            )
        return rag_chain

    def handle_question(self, user_query, name):
        graph_context = ""
        if self.args.useGraphRag:
            self.logger.debug("Step 1: Querying Neo4j graph...")
            try:
                graph_response = self.graph_chain.invoke({"query": user_query})
                graph_context = graph_response.get("result", "")
                self.logger.debug("Graph result:\n%s", graph_context)
            except Exception as e:
                self.logger.error("Graph query failed: %s", e)
                graph_context = ""
        self.logger.debug("Step 2: Querying vector RAG with graph context...")
        try:
            out = self.chat_with_history.invoke({"input": user_query, "graph_context": graph_context}, config={
                                                "configurable": {"session_id": name}})
            if self.args.format == "structured":
                out = CodingAdvice.model_validate_json(out)
        except ValueError as ve:
            self.logger.error(
                "Structured output parsing failed: %s. Showing raw output.", ve)
            return str(ve)
        except Exception as e:
            self.logger.error("Error during chain invocation: %s", e)
            return str(e)
        return out
