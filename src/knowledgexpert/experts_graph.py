import json
import os
import re
from typing import Any, Dict, Optional
from langchain_core.messages import HumanMessage, SystemMessage
from langgraph.graph import StateGraph, END
from langchain_core.runnables import RunnableLambda, RunnableBranch
from pydantic import BaseModel

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
    analyis: str
    references: Optional[list]

    def __str__(self):
        fields = []
        for field, value in self.__dict__.items():
            if value is not None and value != "" and value != []:
                fields.append(f"{field}:\n{value}")
        return f"{'\n\n'.join(fields)}"

class ExpertsGraph:
    def __init__(self, logger, args, default_arg_vals):
        self.args = args
        self.logger = logger
        self.analyst = self._init_expert(logger, args.confDir, "analyst", default_arg_vals, AnalystOutput)
        self.developer = self._init_expert(logger, args.confDir, "developer", default_arg_vals)
        self._setup_graph()

    def _setup_graph(self):
        graph = StateGraph(Dict[str, Any])
        graph.add_node("analyst", RunnableLambda(self.analyst_node))
        graph.add_node("router", RunnableLambda(self.router_node))

        # graph.add_node("developer", RunnableLambda(self.developer_node))

        graph.add_edge("analyst", "router")
        graph.add_edge("router", END)

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
        state["analysis_output"] = response
        return state
    
    def developer_node(self, state):
        analyst_output = str(state["analysis_output"])
        response = self.developer.handle_question(state["input"], state["user_name"], interactions=analyst_output)
        state["analysis_output"] = analyst_output
        state["developer_output"] = response
        return state
    
    def router_node(self, state):
        # Use RunnableBranch for routing
        def routing_predicate(state):
            return state['analysis_output'].classification

        return RunnableBranch(
                (lambda state: routing_predicate(state) == "code-generation-request", RunnableLambda(self.developer_node)),
                # default
                (lambda state: str(state["analysis_output"])))


    def handle_question(self, user_query, name):
        result = self.compiled_graph.invoke({"input": user_query, "user_name": name})
        return result

