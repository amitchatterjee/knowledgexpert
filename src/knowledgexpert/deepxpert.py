from argparse import Namespace
import json
from logging import Logger
import os
import re
from typing import Any, Dict, Optional
from langgraph.graph import StateGraph, END
from langchain_core.runnables import RunnableLambda, RunnableBranch, RunnableParallel
from langchain_core.tools import StructuredTool
from pydantic import BaseModel, Field

from knowledgexpert.expert import Expert
from knowledgexpert.structures import AnalystOutput, CodingOutput

def write_file_tool(code: str, filename: str, directory: str) -> str:
    try:
        if not directory or not filename or not code:
            return "Error: Missing 'filename' or 'code' in input."
        full_path = os.path.join(directory, filename)
        with open(full_path, "w") as f:
            f.write(code)
        return f"Successfully wrote to file: {full_path}"
    except Exception as e:
        return f"Error writing to file: {e}"

write_file = StructuredTool.from_function(
    name="write_file",
    description="Write content to a file. Input: code (str), filename (str).",
    func=write_file_tool,
)

class ExpertsGraph:
    def __init__(self, logger:Logger, default_args:dict, **kwargs):
        self.args = Namespace(**kwargs)
        self.logger = logger

        if not os.path.exists(self.args.workspaceDir):
            os.makedirs(self.args.workspaceDir, exist_ok=True)

        self.analyst = self._init_expert(logger, self.args.confDir, "analyst", default_args, structure=AnalystOutput)
        self.developer = self._init_expert(logger, self.args.confDir, "developer", default_args, structure=CodingOutput)
        self._setup_graph()

    def _setup_graph(self):
        graph = StateGraph(Dict[str, Any])
        graph.add_node("analyst", RunnableLambda(self.analyst_node))
        graph.add_node("request_router", RunnableLambda(self.request_router_node))
        graph.add_node("code_writer_tool", RunnableLambda(self.code_writer_tool_node))

        graph.add_edge("analyst", "request_router")
        graph.add_edge("request_router", "code_writer_tool")
        graph.add_edge("code_writer_tool", END)

        graph.set_entry_point("analyst")
        self.compiled_graph = graph.compile()

    def _replacer(self, match):
        env_var = match.group(1)
        return os.environ.get(env_var, "")

    def _resolve_env_vars(self, args_dict: dict[str, str]) -> dict[str, str]:
        # Replace any string values in args_dict with environment variables if specified as ${ENV}
        pattern = re.compile(r"\$\{([^}]+)\}")
        resolved = {}
        for k, v in args_dict.items():
            if isinstance(v, str):
                #print(k, '=', v)
                #print(pattern.findall(v))
                resolved[k] = pattern.sub(self._replacer, v)
            else:
                resolved[k] = v
        return resolved

    def _init_expert(self, logger, conf_dir, type, default_arg_vals, structure=None):
        config_path = os.path.join(conf_dir, type, "config.json")
        with open(config_path, "r") as f:
            expert_config = json.load(f)
        args_dict = self._resolve_env_vars(expert_config)
        args = default_arg_vals
        args.update(args_dict)
        logger.info(f"Configuration for {type} - {args}")
        return Expert(logger, structure=structure, **args)

    def analyst_node(self, state):
        response = self.analyst.handle_question(state["input"], state["user_name"])
        state["analyst_output"] = response
        return state
    
    def developer_node(self, state):
        analyst_output = f"Analysis:\n{state["analyst_output"].analysis}\n\nCode-generation Requirements:\n{state["analyst_output"].codeGenRequirements}"
        response = self.developer.handle_question(state["input"], state["user_name"], interactions=analyst_output)
        state["developer_output"] = response
        return state
    
    def tester_node(self, state):
        state["tester_output"] = "I am not ready to produce tests yet"
        return state
    
    def implementor_node(self, state):
        state["implementor_output"] = "I am not ready to configure yet"
        return state

    def development_team_node(self, state):
        parallel = RunnableParallel(
            developer=self.developer_node,
            tester=self.tester_node,
            implementor=self.implementor_node
        )
        result = parallel.invoke(state)
        #state.update(result)
        return state

    def request_router_node(self, state):
        def classification(state):
            return state["analyst_output"].classification

        return RunnableBranch(
                (lambda state: classification(state) == "code-generation-request", RunnableLambda(self.development_team_node)),
                (lambda state: classification(state) == "test-generation-request", RunnableLambda(self.tester_node)),
                (lambda state: classification(state) == "config-generation-request", RunnableLambda(self.implementor_node)),
                # default
                (lambda state: state))
    
    def code_writer_tool_node(self, state):
        developer_output = state["developer_output"] if "developer_output" in state else None
        if developer_output:
            result = write_file.run({
                "code": state["developer_output"].code, 
                "directory": self.args.workspaceDir,
                "filename": state["developer_output"].filename})
            state["code_writer_tool_output"] = result
        return state

    def handle_request(self, request, name):
        result = self.compiled_graph.invoke({"input": request, "user_name": name})
        return result

