from argparse import Namespace
import json
from logging import Logger
import os
from typing import Any, Dict
from langgraph.graph import StateGraph, END
from langchain_core.runnables import RunnableLambda, RunnableBranch, RunnableParallel
from langchain_core.tools import StructuredTool

from knowledgexpert.util import resolve_env_vars
from knowledgexpert.raven import Raven
from knowledgexpert.structures import AnalystOutput, CodingOutput, TestingOutput

def write_files_tool(directory: str, ruleset: str, file_name: str, code: str, rule_name: str, test_data: list) -> str:
    file_list = []
    if code:
        if not ruleset or not file_name:
            raise Exception('Either ruleset name or file name not specified')
        
        full_path = os.path.join(directory, 'rules', ruleset, file_name)
        os.makedirs(os.path.dirname(full_path), exist_ok=True)
        with open(full_path, "w") as f:
            f.write(code)
            file_list.append(full_path)
    
    if test_data:
        base_dir = os.path.join(directory, 'test')
        for each in test_data:
            file_name = each.fileName
            full_path = os.path.join(base_dir, file_name)
            os.makedirs(os.path.dirname(full_path), exist_ok=True)
            with open(full_path, "w") as f:
                f.write(each.content)
                file_list.append(full_path)
    return {"files": file_list}

write_files = StructuredTool.from_function(
    name="write_files",
    description="Write rule, configuration, and test data to the workspace",
    func=write_files_tool,
)

class Wolfpack:
    def __init__(self, logger:Logger, raven_default_args:dict, checkpointer=None, **kwargs):
        self.args = Namespace(**kwargs)
        self.logger = logger

        if not os.path.exists(self.args.workspaceDir):
            os.makedirs(self.args.workspaceDir, exist_ok=True)

        self.analyst = self._init_raven(logger, self.args.confDir, "analyst", raven_default_args, structure=AnalystOutput)
        self.developer = self._init_raven(logger, self.args.confDir, "developer", raven_default_args, structure=CodingOutput)
        self.tester = self._init_raven(logger, self.args.confDir, "tester", raven_default_args, structure=TestingOutput)
        self._setup_graph(checkpointer)

    def _setup_graph(self, checkpointer):
        graph = StateGraph(Dict[str, Any])
        graph.add_node("analyst", RunnableLambda(self.analyst_node))
        graph.add_node("request_router", RunnableLambda(self.request_router_node))

        graph.add_edge("analyst", "request_router")
        graph.add_edge("request_router", END)

        graph.set_entry_point("analyst")
        self.compiled_graph = graph.compile(checkpointer=checkpointer)

    def _init_raven(self, logger, conf_dir, type, default_arg_vals, structure=None):
        config_path = os.path.join(conf_dir, type, "config.json")
        with open(config_path, "r") as f:
            expert_config = json.load(f)
        args_dict = resolve_env_vars(expert_config)
        args = default_arg_vals
        args.update(args_dict)
        logger.info(f"Configuration for {type} - {args}")
        return Raven(logger, structure=structure, **args)

    def analyst_node(self, state):
        payload = {"messages": [{"role": "user", "content": state["input"]}], "user_id": state["user_id"], "persona": getattr(self.analyst.args, "persona", None)}
        response = self.analyst.invoke(payload)
        state["analyst_output"] = response
        return state
    
    def developer_node(self, state):
        analyst = state.get("analyst_output")
        analyst_output = f"Analysis:\n{getattr(analyst, 'analysis', '')}\n\nCode-generation Requirements:\n{getattr(analyst, 'codeGenerationRequirements', '')}"
        content = f"Interactions:\n{analyst_output}\n\nQuestion:\n{state['input']}"
        payload = {"messages": [{"role": "user", "content": content}], "user_id": state["user_id"], "persona": getattr(self.developer.args, "persona", None)}
        response = self.developer.invoke(payload)
        state["developer_output"] = response
        return state
    
    def tester_node(self, state):
        analyst = state.get("analyst_output")
        analyst_output = f"Analysis:\n{getattr(analyst, 'analysis', '')}\n\nTest-generation Requirements:\n{getattr(analyst, 'testGenerationRequirements', '')}"
        content = f"Interactions:\n{analyst_output}\n\nQuestion:\n{state['input']}"
        payload = {"messages": [{"role": "user", "content": content}], "user_id": state["user_id"], "persona": getattr(self.tester.args, "persona", None)}
        response = self.tester.invoke(payload)
        state["tester_output"] = response
        return state
    
    def implementor_node(self, state):
        state["implementor_output"] = "I am not ready to configure yet"
        return state

    def development_wolfpack_node(self, state):
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
            if type(state["analyst_output"]) == str:
                raise Exception(f"Expecting AnalystOutput, got str: {state["analyst_output"]}")
            return state["analyst_output"].classification

        # Helper to chain a node with code_writer_tool
        def chain_with_code_writer(node_func):
            return RunnableLambda(node_func) | RunnableLambda(self.code_writer_tool_node)

        return RunnableBranch(
            (lambda state: classification(state) == "code-generation-request", chain_with_code_writer(self.development_wolfpack_node)),
            (lambda state: classification(state) == "test-generation-request", chain_with_code_writer(self.tester_node)),
            (lambda state: classification(state) == "config-generation-request", chain_with_code_writer(self.implementor_node)),
            # default
            (lambda state: state))
    
    def code_writer_tool_node(self, state):
        if getattr(self.args, "skipWriter", False):
            state["file_writer_output"] = {"skipped": True}
            return state
        directory = getattr(self.args, "workspaceDir")
        ruleset = getattr(state.get("analyst_output", None), "ruleset", None)
        file_name = getattr(state.get("developer_output", None), "fileName", None)
        code = getattr(state.get("developer_output", None), "code", None)
        rule_name = getattr(state.get("developer_output", None), "ruleName", None)
        testdata = getattr(state.get("tester_output", None), "content", [])
        result = write_files.run({
            "directory": directory,
            "ruleset": ruleset,
            "file_name": file_name,
            "code": code,
            "rule_name": rule_name,
            "test_data": testdata
        })
        state["file_writer_output"] = result
        return state

    def invoke(self, request, user_id, thread_id=None):
        config={"configurable": {"thread_id": thread_id}}
        result = self.compiled_graph.invoke({"input": request, "user_id": user_id},
                                            config=config)
        return result

