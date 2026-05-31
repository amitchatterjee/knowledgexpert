from dataclasses import dataclass
from typing import Any, Mapping

import chromadb
from opensearchpy import OpenSearch
from langchain_community.vectorstores import OpenSearchVectorSearch
from langchain_chroma import Chroma
from langchain_classic.retrievers import EnsembleRetriever


@dataclass(frozen=True)
class VectorDbConfig:
    provider: str = "chroma"
    host: str = "localhost"
    port: int = 8000
    use_ssl: bool = False
    username: str | None = None
    password: str | None = None
    index_prefix: str | None = None

    @classmethod
    def from_mapping(cls, values: Mapping[str, Any]) -> "VectorDbConfig":
        return cls(
            provider=(values.get("vectorDbProvider") or "chroma").lower(),
            host=values.get("vectorDbHost") or "localhost",
            port=int(values.get("vectorDbPort") or 8000),
            use_ssl=bool(values.get("vectorDbUseSsl") or False),
            username=values.get("vectorDbUsername") or None,
            password=values.get("vectorDbPassword") or None,
            index_prefix=values.get("vectorDbIndexPrefix") or None,
        )

    def with_collection_name(self, logical_name: str) -> str:
        if self.index_prefix:
            return f"{self.index_prefix}{logical_name}"
        return logical_name

    def endpoint_url(self) -> str:
        scheme = "https" if self.use_ssl else "http"
        return f"{scheme}://{self.host}:{self.port}"

    def http_auth(self) -> tuple[str, str] | None:
        if self.username is None or self.password is None:
            return None
        return (self.username, self.password)


def create_vector_client(config: VectorDbConfig):
    if config.provider == "chroma":
        return chromadb.HttpClient(host=config.host, port=config.port)
    if config.provider == "opensearch":
        client_kwargs: dict[str, Any] = {
            "use_ssl": config.use_ssl,
            "verify_certs": False,
            "ssl_assert_hostname": False,
            "ssl_show_warn": False,
        }
        http_auth = config.http_auth()
        if http_auth:
            client_kwargs["http_auth"] = http_auth

        return OpenSearch(config.endpoint_url(), **client_kwargs)
    raise NotImplementedError(
        f"Vector DB provider '{config.provider}' is not implemented yet"
    )


def create_vector_store(
    config: VectorDbConfig,
    collection_name: str,
    embedding_function,
    client=None,
):
    if config.provider == "chroma":
        vector_client = client or create_vector_client(config)
        return Chroma(
            client=vector_client,
            collection_name=config.with_collection_name(collection_name),
            embedding_function=embedding_function,
        )
    if config.provider == "opensearch":
        store_kwargs: dict[str, Any] = {
            "use_ssl": config.use_ssl,
            "verify_certs": False,
            "ssl_assert_hostname": False,
            "ssl_show_warn": False,
            "engine": "faiss",
        }
        http_auth = config.http_auth()
        if http_auth:
            store_kwargs["http_auth"] = http_auth

        return OpenSearchVectorSearch(
            opensearch_url=config.endpoint_url(),
            index_name=config.with_collection_name(collection_name),
            embedding_function=embedding_function,
            **store_kwargs,
        )
    raise NotImplementedError(
        f"Vector DB provider '{config.provider}' is not implemented yet"
    )


def clear_vector_collection(
    config: VectorDbConfig,
    collection_name: str,
    client=None,
) -> None:
    resolved_name = config.with_collection_name(collection_name)
    vector_client = client or create_vector_client(config)

    if config.provider == "chroma":
        if resolved_name in [col.name for col in vector_client.list_collections()]:
            vector_client.delete_collection(resolved_name)
        return

    if config.provider == "opensearch":
        vector_client.indices.delete(index=resolved_name, ignore_unavailable=True)
        return

    raise NotImplementedError(
        f"Vector DB provider '{config.provider}' is not implemented yet"
    )


def create_retriever(
    config: VectorDbConfig,
    base_collections: list[dict[str, Any]],
    ensemble_weights: list[float],
    embeddings_dict: dict[str, Any],
):
    vector_client = None
    if config.provider == "chroma":
        vector_client = create_vector_client(config)
    retrievers = []
    weights = []

    for i, collection_element in enumerate(base_collections):
        retriever_kwargs = {"search_kwargs": {}}
        if collection_element.get("k"):
            retriever_kwargs["search_kwargs"]["k"] = collection_element["k"]
        if (
            collection_element.get("searchAlgorithm") == "similarity_score_threshold"
            and collection_element.get("scoreThreshold") is not None
        ):
            retriever_kwargs["search_kwargs"]["score_threshold"] = collection_element[
                "scoreThreshold"
            ]

        vector_store = create_vector_store(
            config=config,
            collection_name=collection_element["collectionName"],
            embedding_function=embeddings_dict[collection_element["embeddingId"]],
            client=vector_client,
        )

        retrievers.append(
            vector_store.as_retriever(
                search_type=collection_element["searchAlgorithm"],
                **retriever_kwargs,
            )
        )

        if ensemble_weights and i < len(ensemble_weights):
            weights.append(ensemble_weights[i])
        else:
            weights.append(1.0)

    if len(retrievers) == 1:
        return retrievers[0]

    return EnsembleRetriever(retrievers=retrievers, weights=weights)
