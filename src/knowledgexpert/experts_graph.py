import json
import os
import re
from typing import Any, Dict
from langchain_core.messages import HumanMessage, SystemMessage
from langgraph.graph import StateGraph, END
from langchain_core.runnables import RunnableLambda

from knowledgexpert.util import setup_llm
from knowledgexpert.expert import Expert

class ArgsNamespace:
    def __init__(self, d):
        self.__dict__.update(d)
    def __str__(self):
        return f"{self.__class__.__name__}({', '.join(f'{k}={v}' for k, v in self.__dict__.items())})"
    def __repr__(self):
        return self.__str()

class ExpertsGraph:
    def __init__(self, logger, args, default_arg_vals):
        self.args = args
        self.logger = logger
        self.coding_expert = self._init_expert(logger, args.confDir, "coding-expert", default_arg_vals)
        self.frontline_expert = self._init_expert(logger, args.confDir, "frontline-expert", default_arg_vals)
        self._setup_graph()

    def _setup_graph(self):
        graph = StateGraph(Dict[str, Any])
        graph.add_node("frontline_expert", RunnableLambda(self.frontline_expert_node))
        graph.add_node("coding_expert", RunnableLambda(self.coding_expert_node))

        graph.add_edge("frontline_expert", "coding_expert")
        graph.add_edge("coding_expert", END)

        graph.set_entry_point("frontline_expert")
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

    def _init_expert(self, logger, conf_dir, type, default_arg_vals):
        config_path = os.path.join(conf_dir, type, "config.json")
        with open(config_path, "r") as f:
            expert_config = json.load(f)
        args_dict = self._resolve_env_vars(expert_config)
        args = ArgsNamespace(args_dict)
        merged_args = vars(default_arg_vals)
        merged_args.update(args_dict)
        args = ArgsNamespace(merged_args)
        logger.info(f"Configuration for {type} - {args}")
        return Expert(args, logger)

    def frontline_expert_node(self, state):
        response = self.frontline_expert.handle_question(state["input"], state["user_name"])
        state["frontline_expert_output"] = response
        return state
    
    def coding_expert_node(self, state):
        response = self.coding_expert.handle_question(state["input"], state["user_name"], interactions=state["frontline_expert_output"])
        state["coding_expert_output"] = response
        return state

    def handle_question(self, user_query, name):
        result = self.compiled_graph.invoke({"input": user_query, "user_name": name})
        return result

