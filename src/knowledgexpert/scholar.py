import os
from argparse import Namespace
from logging import Logger
from knowledgexpert.expert import Expert
import glob
from langchain.text_splitter import MarkdownTextSplitter, PythonCodeTextSplitter

def python_chunker(text, chunk_size):
    splitter = PythonCodeTextSplitter(chunk_size=chunk_size, chunk_overlap=100)
    return splitter.split_text(text)

def markdown_chunker(text, chunk_size):
    splitter = MarkdownTextSplitter(chunk_size=chunk_size, chunk_overlap=100)
    return splitter.split_text(text)

class Scholar:
    def __init__(self, logger: Logger, args: dict, **kwargs):
        self.args = Namespace(**kwargs)
        self.logger = logger
        self.expert = Expert(logger, **args)
        self.split_size = getattr(self.args, 'split_size', 1000)

    def handle_question(self, user_query, name, documents_path):
        file_patterns = [os.path.join(documents_path, '*.md'), os.path.join(documents_path, '*.py')]
        files = []
        for pattern in file_patterns:
            files.extend(glob.glob(pattern))
        all_chunks = []
        for file_path in files:
            with open(file_path, 'r', encoding='utf-8') as f:
                text = f.read()
            if file_path.endswith('.py'):
                chunks = python_chunker(text, self.split_size)
            elif file_path.endswith('.md'):
                chunks = markdown_chunker(text, self.split_size)
            else:
                continue
            all_chunks.extend([(file_path, chunk) for chunk in chunks])
        results = []
        for file_path, chunk in all_chunks:
            result = self.expert.handle_question(user_query, name, interactions=chunk)
            results.append({"file": file_path, "chunk": chunk, "result": result})
        return results
