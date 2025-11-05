from argparse import Namespace
import asyncio
import json
from logging import Logger
import logging
import os
from typing import Any
from anthropic import BaseModel
import httpx
from langchain_mcp_adapters.client import MultiServerMCPClient
from langchain.agents import create_agent
from langchain.agents.structured_output import ToolStrategy

from knowledgexpert.util import setup_llm

class Answer(BaseModel):
    summary: str
    answer: str
    reference: str

default_conf_dir = os.path.join(os.path.expanduser(
    "~"), ".knowledgexpert", "conf", "raven")

class Raven:
    def __init__(self, logger: Logger, structure:Any=None, **kwargs):       
        self.args = Namespace(**kwargs)
        self.logger = logger
        self.structure = structure
        self.prompt_dir = self.args.promptDir if self.args.promptDir else default_conf_dir

        logging.getLogger("langchain").setLevel(self.logger.level)
        # Suppress HTTP request/response messages
        logging.getLogger("httpx").setLevel(logging.WARNING)
        logging.getLogger("urllib3").setLevel(logging.WARNING)
        logging.getLogger("requests").setLevel(logging.WARNING)
        # Suppress telemetry messages
        logging.getLogger("langchain.telemetry").setLevel(logging.WARNING)
        logging.getLogger("langchain_community.telemetry").setLevel(logging.WARNING)

        model = setup_llm(llm_model=self.args.llmModel, 
                        llm_api_endpoint=self.args.llmApiEndpoint, 
                        output_format=self.args.format,)

        tools = []
        tools = asyncio.run(self._setup_mcp_tools(self.args.mcpConfig, insecure=self.args.mcpInsecure))

        prompt_path = os.path.join(self.prompt_dir, "mcp_prompt.txt")
        mcp_prompt = "You are a helpful assistant. Be concise and accurate."
        if os.path.exists(prompt_path):
            with open(prompt_path, "r", encoding="utf-8") as pf:
                mcp_prompt = pf.read()
            
        else:
            self.logger.warning("MCP prompt file not found: %s", prompt_path)

        self.agent = create_agent(
            model=model,
            tools=tools,
            system_prompt=mcp_prompt,
            response_format=ToolStrategy(self.structure)
    )

    async def _setup_mcp_tools(self, mcp_config, insecure: bool = False):
            path = os.path.expanduser(mcp_config)
            verify = False if insecure else True
            if not verify:
                self.logger.warning("TLS verification is disabled for MCP connections. This is insecure and should only be used for self-signed certificates.")

            def httpx_client_factory(headers: dict[str, str] | None = None, timeout: httpx.Timeout | None = None, auth: httpx.Auth | None = None) -> httpx.AsyncClient:
                client_headers = headers.copy() if headers else {}
                return httpx.AsyncClient(verify=verify, headers=client_headers, timeout=timeout, auth=auth)

            with open(path, "r", encoding="utf-8") as f:
                config = json.load(f)

            for v in config.values():
                if v.get("transport") in ("streamable_http", "sse"):
                    v["httpx_client_factory"] = httpx_client_factory

            client = MultiServerMCPClient(config)
            tools = await client.get_tools()
            # Some MCP-provided tools are StructuredTool instances that only
            # implement an async coroutine (they have `coroutine` but no
            # synchronous `func`). Langchain's tooling may attempt to call
            # tools synchronously (for threaded execution) which raises
            # "StructuredTool does not support sync invocation." To support
            # those sync call-sites, provide a thin synchronous wrapper that
            # runs the coroutine in a fresh event loop when invoked.
            for t in tools:
                # Only wrap tools that expose a coroutine but no sync func
                try:
                    has_coroutine = getattr(t, "coroutine", None) is not None
                    has_func = getattr(t, "func", None) is not None
                except Exception:
                    has_coroutine = False
                    has_func = False
                if has_coroutine and not has_func:
                    coro = t.coroutine

                    def _make_sync(coro_fn):
                        def _sync_wrapper(*args, **kwargs):
                            return asyncio.run(coro_fn(*args, **kwargs))

                        return _sync_wrapper

                    t.func = _make_sync(coro)
            self.logger.debug("Loaded tools based on configuration file: %s", mcp_config)
            return tools
    
    def invoke(self, input:dict):
        return self.agent.invoke(input)

    def ainvoke(self, input:dict):
        return self.agent.ainvoke(input)

