import json
import os
from argparse import Namespace
from logging import Logger
from typing import Optional

from langchain_text_splitters import TokenTextSplitter
from langchain_community.document_loaders import TextLoader, DirectoryLoader
from knowledgexpert.expert import Expert
from knowledgexpert.util import resolve_env_vars
import glob
from langchain.text_splitter import MarkdownTextSplitter, PythonCodeTextSplitter
from pydantic import BaseModel, Field
from knowledgexpert.chunker import create_chunks
from knowledgexpert.structures import ScholarOutput

class Scholar:
    def __init__(self, logger: Logger, args: dict, **kwargs):
        self.args = Namespace(**kwargs)
        self.logger = logger

        self.py_splitter = PythonCodeTextSplitter(chunk_size=args.chunkSize, chunk_overlap=args.chunkOverlap)
        self.md_splitter = MarkdownTextSplitter(chunk_size=args.chunkSize, chunk_overlap=args.chunkOverlap)
        self.txt_splitter = TokenTextSplitter(chunk_size=args.chunkSize, chunk_overlap=args.chunkOverlap)

        self.expert = self._init_expert(logger, self.args.confDir, args, structure=ScholarOutput)

    def _init_expert(self, logger, conf_dir, default_arg_vals, structure=None):
        config_path = os.path.join(conf_dir, "config.json")
        with open(config_path, "r") as f:
            expert_config = json.load(f)
        args_dict = resolve_env_vars(expert_config)
        args = default_arg_vals
        args.update(args_dict)
        logger.info(f"Configuration for expert - {args}")
        return Expert(logger, structure=structure, **args)

    def handle_question(self, user_query, name, documents_path):
        all_docs = []
        for document_spec in self.args.documents:
            dir_path, glob_pattern = document_spec.split(';')
            if not glob_pattern:
                glob = ["**/*.py", "**/*.md"]
            else:
                glob = glob_pattern.split(',')
            
            self.logger.debug('Loading documents from: {%s}', dir_path)
            loader = DirectoryLoader(
                dir_path,
                glob=glob,
                loader_cls=TextLoader,
                recursive=True)
            docs = loader.load()
            self.logger.debug("Loaded %d document", len(docs))
            all_docs.append(docs)
        results = []
        for each in all_docs:
            chunks = create_chunks(each, py_splitter=self.py_splitter, md_splitter=self.md_splitter, txt_splitter=self.txt_splitter)
            for chunk in chunks:
                result = self.expert.handle_question(user_query, name, interactions=chunk)
                results.append(result)
        return results

    def print_chunk_info(self, chunk):
        print(f"Source: {chunk.metadata.get('source', '')}")
        print(f"Metadata: {chunk.metadata}")
        print(f"Content:\n{getattr(chunk, 'page_content', '')}\n{'-'*60}")