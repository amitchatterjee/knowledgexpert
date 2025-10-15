import json
import os
from argparse import Namespace
from logging import Logger

from langchain_text_splitters import TokenTextSplitter
from langchain_community.document_loaders import TextLoader, DirectoryLoader, UnstructuredHTMLLoader
from knowledgexpert.expert import Expert
from knowledgexpert.util import resolve_env_vars
from langchain.text_splitter import MarkdownTextSplitter, PythonCodeTextSplitter
from knowledgexpert.chunker import create_chunks
from knowledgexpert.structures import BookWormOutput
from knowledgexpert.html_splitter import HTMLTextSplitter


class BookWorm:
    def __init__(self, logger: Logger, expert_default_args: dict, **kwargs):
        self.args = Namespace(**kwargs)
        self.logger = logger

        self.py_splitter = PythonCodeTextSplitter(chunk_size=self.args.chunkSize, chunk_overlap=self.args.chunkOverlap)
        self.md_splitter = MarkdownTextSplitter(chunk_size=self.args.chunkSize, chunk_overlap=self.args.chunkOverlap)
        self.txt_splitter = TokenTextSplitter(chunk_size=self.args.chunkSize, chunk_overlap=self.args.chunkOverlap)
        self.html_splitter = HTMLTextSplitter(chunk_size=self.args.chunkSize, chunk_overlap=self.args.chunkOverlap)

        self.expert = self._init_expert(logger, self.args.confDir, expert_default_args, BookWormOutput)

    def _init_expert(self, logger, conf_dir, default_arg_vals, structure):
        config_path = os.path.join(conf_dir, "config.json")
        with open(config_path, "r") as f:
            expert_config = json.load(f)
        args_dict = resolve_env_vars(expert_config)
        args = default_arg_vals
        args.update(args_dict)
        logger.info(f"Configuration for expert - {args}")
        return Expert(logger, structure=structure, **args)

    def handle_question(self, user_query, name, documents):
        all_docs = []
        for document_spec in documents:
            splits = document_spec.split(';')
            dir_path = splits[0]
            glob_patterns = splits[1].split(',') if len(splits) > 1 else ["**/*.py", "**/*.md", "**/*.html", "**/*.htm"]
            self.logger.debug('Loading documents from: {%s}', dir_path)
            
            loader_map = {
                '.py': TextLoader,
                '.md': TextLoader,
                '.txt': TextLoader,
                '.html': UnstructuredHTMLLoader,
                '.htm': UnstructuredHTMLLoader
            }

            # Group patterns by loader class
            patterns_by_loader = {}
            for pattern in glob_patterns:
                ext = os.path.splitext(pattern)[1].lower()
                loader_cls = loader_map.get(ext)
                if loader_cls:
                    patterns_by_loader.setdefault(loader_cls, []).append(pattern)
            # Load documents for each loader class
            for loader_cls, patterns in patterns_by_loader.items():
                loader = DirectoryLoader(
                    dir_path,
                    glob=patterns,
                    loader_cls=loader_cls,
                    recursive=True)
                docs = loader.load()
            self.logger.debug("Loaded %d document", len(docs))
            all_docs.extend(docs)
        results = []

        all_docs.sort(key=lambda doc: os.path.basename(doc.metadata["source"]))

        for doc in all_docs:
            chunks = create_chunks(([doc],{}), py_splitter=self.py_splitter, md_splitter=self.md_splitter, txt_splitter=self.txt_splitter, html_splitter=self.html_splitter)
            relevant_findings=[]
            for chunk in chunks:
                self.logger.debug(f"Processing chunk from {doc.metadata.get('source', '')}")
                input = f"<documentSegment>\nDocument Segment:\n{chunk}</documentSegment>\n\n<relevantFindings>\nRelevant Findings:\n{self.format_list(relevant_findings)}<relevantFindings>\n\n"
                result = self.expert.handle_question(user_query, name, interactions=input)
                if result.informationFound:
                    self.logger.debug(f"Found relevant information in chunk from {doc.metadata.get('source', '')}")
                    relevant_findings.append(result.explanation)
                    results.append(result)
        return results
    
    def format_list(self, l:list):
        return '\n'.join([f"{idx+1}. {item}" for idx, item in enumerate(l)])

    def print_chunk_info(self, chunk):
        print(f"Source: {chunk.metadata.get('source', '')}")
        print(f"Metadata: {chunk.metadata}")
        print(f"Content:\n{getattr(chunk, 'page_content', '')}\n{'-'*60}")