def create_chunks(doc_tuple, md_splitter, py_splitter, txt_splitter):
    doc_chunks = []
    for each in doc_tuple[0]:
        source = each.metadata.get('source', '')
        if source.endswith('.py'):
            # Use PythonCodeTextSplitter for Python files
            py_chunks = py_splitter.split_text(each.page_content)
            for chunk in py_chunks:
                if isinstance(chunk, str) and chunk.strip():
                    doc_chunk = type(each)(page_content=chunk, metadata=each.metadata)
                    doc_chunk.metadata.update({'type': 'code', 'language': 'python'})
                    doc_chunk.metadata.update(doc_tuple[1])
                    doc_chunks.append(doc_chunk)
        elif source.endswith('.md'):
            # Use MarkdownTextSplitter for markdown files
            md_chunks = md_splitter.split_text(each.page_content)
            for chunk in md_chunks:
                if isinstance(chunk, str) and chunk.strip():
                    doc_chunk = type(each)(page_content=chunk, metadata=each.metadata)
                    doc_chunk.metadata.update(doc_tuple[1])
                    doc_chunks.append(doc_chunk)
        else:
            # Use TextTokenSplitter for other text files as fallback
            txt_chunks = txt_splitter.split_text(each.page_content)
            for chunk in txt_chunks:
                if isinstance(chunk, str) and chunk.strip():
                    doc_chunk = type(each)(page_content=chunk, metadata=each.metadata)
                    doc_chunk.metadata.update(doc_tuple[1])
                    doc_chunks.append(doc_chunk)
    return doc_chunks
