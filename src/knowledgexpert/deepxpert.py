from argparse import Namespace
import json
from logging import Logger
import os
import re
from typing import Any, Dict
from langgraph.graph import StateGraph, END
from langchain_core.runnables import RunnableLambda, RunnableBranch, RunnableParallel
from langchain_core.tools import StructuredTool

from knowledgexpert.util import resolve_env_vars
from knowledgexpert.expert import Expert
from knowledgexpert.structures import AnalystOutput, CodingOutput, TestingOutput, TestFileOutput

def write_files_tool(directory: str, ruleset: str, filename: str, code: str, rulename: str, testdata: list) -> str:
    try:
        file_list = []
        if ruleset and filename and code:
            full_path = os.path.join(directory, 'rules', ruleset, filename)
            os.makedirs(os.path.dirname(full_path), exist_ok=True)
            with open(full_path, "w") as f:
                f.write(code)
                file_list.append(full_path)
        
        if testdata:
            test_dir = os.path.join(directory, 'test', 'vector', rulename)
            os.makedirs(test_dir, exist_ok=True)
            for each in testdata:
                file_name = each.filename
                full_path = os.path.join(test_dir, file_name)
                with open(full_path, "w") as f:
                    f.write(each.content)
                    file_list.append(full_path)
        return f"Successfully wrote files: {file_list}"
    except Exception as e:
        return f"Error creating files: {e}"

write_files = StructuredTool.from_function(
    name="write_files",
    description="Write rule, configuration, and tests to the workspace",
    func=write_files_tool,
)

class DeepXpert:
    def __init__(self, logger:Logger, default_args:dict, **kwargs):
        self.args = Namespace(**kwargs)
        self.logger = logger

        if not os.path.exists(self.args.workspaceDir):
            os.makedirs(self.args.workspaceDir, exist_ok=True)

        self.analyst = self._init_expert(logger, self.args.confDir, "analyst", default_args, structure=AnalystOutput)
        self.developer = self._init_expert(logger, self.args.confDir, "developer", default_args, structure=CodingOutput)
        self.tester = self._init_expert(logger, self.args.confDir, "tester", default_args, structure=TestingOutput)
        self._setup_graph()

    def _setup_graph(self):
        graph = StateGraph(Dict[str, Any])
        graph.add_node("analyst", RunnableLambda(self.analyst_node))
        graph.add_node("request_router", RunnableLambda(self.request_router_node))

        graph.add_edge("analyst", "request_router")
        graph.add_edge("request_router", END)

        graph.set_entry_point("analyst")
        self.compiled_graph = graph.compile()

    def _init_expert(self, logger, conf_dir, type, default_arg_vals, structure=None):
        config_path = os.path.join(conf_dir, type, "config.json")
        with open(config_path, "r") as f:
            expert_config = json.load(f)
        args_dict = resolve_env_vars(expert_config)
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
        analyst_output = f"Analysis:\n{state["analyst_output"].analysis}\n\nTest-generation Requirements:\n{state["analyst_output"].testGenRequirements}"
        response = self.tester.handle_question(state["input"], state["user_name"], interactions=analyst_output)
        state["tester_output"] = response
    
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
            #print(">>>>>>>>>>", state)
            return state["analyst_output"].classification

        # Helper to chain a node with code_writer_tool
        def chain_with_code_writer(node_func):
            return RunnableLambda(node_func) | RunnableLambda(self.code_writer_tool_node)

        return RunnableBranch(
            (lambda state: classification(state) == "code-generation-request", chain_with_code_writer(self.development_team_node)),
            (lambda state: classification(state) == "test-generation-request", chain_with_code_writer(self.tester_node)),
            (lambda state: classification(state) == "config-generation-request", chain_with_code_writer(self.implementor_node)),
            # default
            (lambda state: state))
    
    def code_writer_tool_node(self, state):
        directory = getattr(self.args, "workspaceDir")
        ruleset = getattr(state.get("analyst_output", None), "ruleset", None)
        filename = getattr(state.get("developer_output", None), "filename", None)
        code = getattr(state.get("developer_output", None), "code", None)
        rulename = getattr(state.get("developer_output", None), "rulename", None)
        testdata = getattr(state.get("tester_output", None), "content", [])
        result = write_files.run({
            "directory": directory,
            "ruleset": ruleset,
            "filename": filename,
            "code": code,
            "rulename": rulename,
            "testdata": testdata
        })
        state["code_writer_tool_output"] = result
        return state

    def handle_request(self, request, name):
        result = self.compiled_graph.invoke({"input": request, "user_name": name})
        return result

