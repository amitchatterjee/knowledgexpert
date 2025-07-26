import os
from typing import Optional
import chromadb
import string

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

# History directory remains as before
hist_dir = os.path.join(os.path.expanduser("~"), ".knowledgexpert", "history")
os.makedirs(hist_dir, exist_ok=True)

default_prompt_dir = os.path.join(os.path.expanduser("~"), ".knowledgexpert", "conf", "expert")

class CodingAdvice(BaseModel):
    summary: Optional[str] = Field("A one-line summary of the code snippet")
    description: Optional[str] = Field(description = "Description of the code snippet")
    code: str = Field(description="A Python Code Snippet")
    explanation: Optional[str] = Field(description="Detailed explaination of the code")
    references: Optional[list] = Field(description = "A list of URLs containing more information")

class Expert:
    def __init__(self, args, parent_logger):
        self.args = args
        self.logger = parent_logger        
        self.prompt_dir = args.promptDir if args.promptDir else default_prompt_dir
        self.embeddings = self._setup_embeddings()
        self.retriever = self._setup_vector_store()
        self.llm = self._setup_llm()
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

    def _is_text_file(self, filepath, blocksize=512):
        try:
            with open(filepath, 'rb') as f:
                chunk = f.read(blocksize)
                if not chunk:
                    return True
                if b'\x00' in chunk:
                    return False
                text_characters = bytes(string.printable, 'ascii')
                nontext = [b for b in chunk if b not in text_characters]
                return float(len(nontext)) / len(chunk) < 0.30
        except Exception:
            return False

    def _build_faiss_store_from_context(self):
        additional_context = []
        context_paths = self.args.contextPaths
        embeddings = self.embeddings
        if context_paths:
            for path in context_paths:
                if os.path.isdir(path):
                    for root, _, files in os.walk(path):
                        for file in files:
                            file_path = os.path.join(root, file)
                            if not self.is_text_file(file_path):
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

    def _setup_embeddings(self):
        if self.args.embeddingApiUrl:
            return HuggingFaceInferenceAPIEmbeddings(
                api_url=self.args.embeddingApiUrl,
                model_name=self.args.embeddingModel,
                api_key=""
            )
        else:
            return HuggingFaceEmbeddings(model_name=self.args.embeddingModel)

    def _setup_vector_store(self):
        faiss_store = self._build_faiss_store_from_context()
        chroma_client = chromadb.HttpClient(host=self.args.chromaHost, port=self.args.chromaPort)
        vectorDb_kwargs = {}
        if self.args.searchAlgorithm == "similarity_score_threshold" and self.args.scoreThreshold is not None:
            vectorDb_kwargs["search_kwargs"] = {"score_threshold": self.args.scoreThreshold}
        vectorDb = Chroma(
            client=chroma_client,
            collection_name=self.args.baseCollection,
            embedding_function=self.embeddings
        )
        if faiss_store:
            retriever = EnsembleRetriever(
                retrievers=[vectorDb.as_retriever(search_type=self.args.searchAlgorithm, **vectorDb_kwargs), faiss_store.as_retriever()],
                weights=self.args.ensembleWeights
            )
        else:
            retriever = vectorDb.as_retriever(search_type=self.args.searchAlgorithm, **vectorDb_kwargs)
        return retriever

    def _setup_llm(self):
        model_provider = self.args.llmModel.split(":")[0]
        if model_provider == 'openai' or model_provider == 'ollama':
            return init_chat_model(
                self.args.llmModel,
                base_url=self.args.llmApiEndpoint,
                temperature=0,
                streaming=True,
                model_kwargs={"response_format": {"type": "json_object"}} if self.args.format == "structured" else {}
            )
        else:
            return init_chat_model(
                self.args.llmModel,
                base_url=self.args.llmApiEndpoint,
                temperature=0,
                streaming=True
            )

    def _setup_graph_chain(self):
        graph = Neo4jGraph(
            url=self.args.neo4jUri,
            username=self.args.neo4jUser,
            password=self.args.neo4jPassword
        )
        graph_prompt_path = os.path.join(self.prompt_dir, "graph_prompt.txt")
        with open(graph_prompt_path, "r", encoding="utf-8") as f:
            system_prompt_text = f.read()

        system_prompt = SystemMessagePromptTemplate.from_template(system_prompt_text)
        human_prompt = HumanMessagePromptTemplate.from_template("{query}")
        chat_prompt = ChatPromptTemplate.from_messages([system_prompt, human_prompt])
        graph_llm = init_chat_model(self.args.graphLlmModel, base_url=self.args.graphLlmApiEndpoint)
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
            out = self.chat_with_history.invoke({"input": user_query, "graph_context": graph_context}, config={"configurable": {"session_id": name}})
            if self.args.format == "structured":
                out = CodingAdvice.model_validate_json(out)
        except ValueError as ve:
            self.logger.error("Structured output parsing failed: %s. Showing raw output.", ve)
            return str(ve)
        except Exception as e:
            self.logger.error("Error during chain invocation: %s", e)
            return str(e)
        return out


