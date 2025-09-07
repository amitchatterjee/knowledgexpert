import os
import string
from langchain_community.document_loaders import TextLoader
from langchain.text_splitter import RecursiveCharacterTextSplitter
from langchain_community.vectorstores import FAISS
from langchain.chat_models.base import init_chat_model
from langchain_huggingface import HuggingFaceEmbeddings
from langchain_community.embeddings import HuggingFaceInferenceAPIEmbeddings
from langchain_huggingface import HuggingFaceEmbeddings
from langchain_community.embeddings import HuggingFaceInferenceAPIEmbeddings

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
                            loader = TextLoader(
                                file_path, encoding="utf-8", autodetect_encoding=True)
                            additional_context.extend(loader.load())
                        except Exception:
                            continue
            elif os.path.isfile(path):
                try:
                    loader = TextLoader(
                        path, encoding="utf-8", autodetect_encoding=True)
                    additional_context.extend(loader.load())
                except Exception:
                    continue

    if additional_context:
        text_splitter = RecursiveCharacterTextSplitter(
            chunk_size=1000, chunk_overlap=100)
        docs = text_splitter.split_documents(additional_context)
        faiss_store = FAISS.from_documents(docs, embeddings)
        return faiss_store
    return None

def is_text_file(filepath, blocksize=512):
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

def setup_llm(llmModel, llmApiEndpoint, output_format):
    model_provider = llmModel.split(":")[0]
    if model_provider == 'openai' or model_provider == 'ollama':
        return init_chat_model(
            llmModel,
            base_url=llmApiEndpoint,
            temperature=0,
            streaming=True,
            model_kwargs={"response_format": {"type": "json_object"}
                          } if output_format == "structured" else {},
        )
    else:
        return init_chat_model(
            llmModel,
            base_url=llmApiEndpoint,
            temperature=0,
            streaming=True,
        )

def setup_embeddings(embeddingModel, embeddingApiUrl):
    if embeddingApiUrl:
        return HuggingFaceInferenceAPIEmbeddings(
            api_url=embeddingApiUrl,
            model_name=embeddingModel,
            api_key=""
        )
    else:
        return HuggingFaceEmbeddings(model_name=embeddingModel)
