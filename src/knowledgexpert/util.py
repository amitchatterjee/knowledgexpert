import re
import os

import string
from langchain.chat_models.base import init_chat_model
from langchain_community.embeddings import HuggingFaceInferenceAPIEmbeddings
from langchain_openai import OpenAIEmbeddings
from langchain_ollama import OllamaEmbeddings

def replacer(match):
    env_var = match.group(1)
    return os.environ.get(env_var, "")

def resolve_env_vars(args_dict: dict[str, str]) -> dict[str, str]:
    pattern = re.compile(r"\$\{([^}]+)\}")
    def resolve_value(val):
        if isinstance(val, str):
            return pattern.sub(replacer, val)
        elif isinstance(val, dict):
            return resolve_env_vars(val)
        elif isinstance(val, (list, tuple, set)):
            resolved_collection = []
            for item in val:
                if isinstance(item, str):
                    resolved_collection.append(pattern.sub(replacer, item))
                elif isinstance(item, dict):
                    resolved_collection.append(resolve_env_vars(item))
                else:
                    resolved_collection.append(item)
            # Return the same type as input
            if isinstance(val, tuple):
                return tuple(resolved_collection)
            elif isinstance(val, set):
                return set(resolved_collection)
            else:
                return resolved_collection
        else:
            return val
    resolved = {}
    for k, v in args_dict.items():
        resolved[k] = resolve_value(v)
    return resolved


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


def setup_llm(llm_model, llm_api_endpoint, output_format):
    model_provider = llm_model.split(":")[0]
    if model_provider == 'openai' or model_provider == 'ollama':
        model = init_chat_model(
            llm_model,
            base_url=llm_api_endpoint,
            temperature=0,
            streaming=True,
            model_kwargs={"response_format": {"type": "json_object"}
                          } if output_format == "structured" else {},
        )
    else:
        model = init_chat_model(
            llm_model,
            base_url=llm_api_endpoint,
            temperature=0,
            streaming=True,
        )
    return model

def embedding_mapper(embedding, def_embedding_provider, def_embedding_api_url, def_embedding_model):
    if embedding:
        tokens = embedding.split('|')
        embedding_id = tokens[0] if tokens[0] else 'default'
        embedding_provider = tokens[1] if len(tokens) > 1 and tokens[1] else def_embedding_provider
        embedding_api_url = tokens[2] if len(tokens) > 2 and tokens[2] else def_embedding_api_url
        embedding_model = tokens[3] if len(tokens) > 3 and tokens[3] else def_embedding_model
    else:
        embedding_id = 'default'
        embedding_provider = def_embedding_provider
        embedding_api_url = def_embedding_api_url
        embedding_model = def_embedding_model
    to_dict = {'embeddingId': embedding_id, 'embeddingProvider': embedding_provider, 'embeddingApiUrl': embedding_api_url, 'embeddingModel': embedding_model}
    return to_dict

def setup_embedding(embedding):
    if embedding['embeddingProvider'] == "openai":
        return OpenAIEmbeddings(model=embedding['embeddingModel'])
    elif embedding['embeddingProvider'] == "huggingface":
        return HuggingFaceInferenceAPIEmbeddings(
            api_url=embedding['embeddingApiUrl'],
            model_name=embedding['embeddingModel'],
            api_key="")
    
    elif 'embeddingApiUrl' in embedding and embedding['embeddingApiUrl']:
        return OllamaEmbeddings(
            model=embedding['embeddingModel'],
            base_url=embedding.get('embeddingApiUrl'))
    else:
        raise ValueError(f"embeddingApiUrl is required for huggingface provider (embeddingId: {embedding.get('embeddingId', 'unknown')})")
