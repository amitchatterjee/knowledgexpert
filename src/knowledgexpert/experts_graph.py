import json
import os
import re
from typing import Any, Dict, Optional
from langgraph.graph import StateGraph, END
from langchain_core.runnables import RunnableLambda, RunnableBranch, RunnableParallel
from langchain_core.tools import StructuredTool
from pydantic import BaseModel, Field

from knowledgexpert.util import setup_llm
from knowledgexpert.expert import Expert

class ArgsNamespace:
    def __init__(self, d):
        self.__dict__.update(d)
    def __str__(self):
        return f"{self.__class__.__name__}({', '.join(f'{k}={v}' for k, v in self.__dict__.items())})"
    def __repr__(self):
        return self.__str()

class AnalystOutput(BaseModel):
    summary: str
    classification: str
    codeGenRequirements: str
    configGenRequirements: str
    testGenRequirements: str
    analysis: str
    references: Optional[list]

    def __str__(self):
        fields = []
        for field, value in self.__dict__.items():
            if value is not None and value != "" and value != []:
                fields.append(f"{field}:\n{value}")
        return f"{'\n\n'.join(fields)}"


class CodingOutput(BaseModel):
    summary: Optional[str] = Field("A one-line summary of the code snippet")
    description: Optional[str] = Field(
        description="Description of the code snippet")
    code: str = Field(description="A Python Code Snippet")
    filename: str = Field(description="Python file name")
    explanation: Optional[str] = Field(
        description="Detailed explanation of the code")
    references: Optional[list] = Field(
        description="A list of URLs containing more information")
    
    def __str__(self):
        fields = []
        for field, value in self.__dict__.items():
            if value is not None and value != "" and value != []:
                fields.append(f"{field}:\n{value}")
        return f"{'\n\n'.join(fields)}"

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
    def __init__(self, logger, args, default_arg_vals):
        self.args = args
        self.logger = logger

        if not os.path.exists(args.workspaceDir):
            os.makedirs(args.workspaceDir, exist_ok=True)

        self.analyst = self._init_expert(logger, args.confDir, "analyst", default_arg_vals, AnalystOutput)
        self.developer = self._init_expert(logger, args.confDir, "developer", default_arg_vals, CodingOutput)
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
        args = ArgsNamespace(args_dict)
        merged_args = vars(default_arg_vals)
        merged_args.update(args_dict)
        args = ArgsNamespace(merged_args)
        logger.info(f"Configuration for {type} - {args}")
        return Expert(args, logger, structure)

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
        return {"tester_output":"I am not ready to produce tests yet"}
    
    def implementor_node(self, state):
        return {"implementor_output":"I am not ready to configure yet"}

    def development_tasks_node(self, state):
        parallel = RunnableParallel(
            developer=self.developer_node,
            tester=self.tester_node,
            implementor=self.implementor_node
        )
        result = parallel.invoke(state)
        state.update(result)
        return state

    def request_router_node(self, state):
        def routing_predicate(state):
            return state["analyst_output"].classification

        return RunnableBranch(
                (lambda state: routing_predicate(state) == "code-generation-request", RunnableLambda(self.development_tasks_node)),
                (lambda state: routing_predicate(state) == "test-generation-request", RunnableLambda(self.tester_node)),
                (lambda state: routing_predicate(state) == "config-generation-request", RunnableLambda(self.implementor_node)),
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

    def handle_question(self, request, name):
        result = self.compiled_graph.invoke({"input": request, "user_name": name})
        return result

