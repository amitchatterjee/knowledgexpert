import json
import os
from argparse import Namespace
from logging import Logger
from knowledgexpert.expert import Expert
from knowledgexpert.util import resolve_env_vars
import glob
from langchain.text_splitter import MarkdownTextSplitter, PythonCodeTextSplitter
from pydantic import BaseModel, Field

def python_chunker(text, chunk_size):
    splitter = PythonCodeTextSplitter(chunk_size=chunk_size, chunk_overlap=100)
    return splitter.split_text(text)

def markdown_chunker(text, chunk_size):
    splitter = MarkdownTextSplitter(chunk_size=chunk_size, chunk_overlap=100)
    return splitter.split_text(text)

def ScholarOutput(BaseModel):
    #TODO
    pass

class Scholar:
    def __init__(self, logger: Logger, args: dict, **kwargs):
        self.args = Namespace(**kwargs)
        self.logger = logger
        self.expert = self._init_expert(logger, self.args.confDir, args, structure=ScholarOutput)
        self.split_size = self.args.splitSize

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
        file_patterns = [os.path.join(documents_path, '*.md'), os.path.join(documents_path, '*.py')]
        files = []
        for pattern in file_patterns:
            files.extend(glob.glob(pattern))
        results = []
        for file_path in files:
            with open(file_path, 'r', encoding='utf-8') as f:
                text = f.read()
            if file_path.endswith('.py'):
                chunks = python_chunker(text, self.split_size)
            elif file_path.endswith('.md'):
                chunks = markdown_chunker(text, self.split_size)
            else:
                continue
            for chunk in chunks:
                result = self.expert.handle_question(user_query, name, interactions=chunk)
                results.append(result)
        return results
