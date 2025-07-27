from typing import Any, Dict
from langchain_core.messages import HumanMessage, SystemMessage
from langgraph.graph import StateGraph, END
from langchain_core.runnables import RunnableLambda

from knowledgexpert.util import setup_llm

class ExpertsGraph:
    def __init__(self, args, logger):
        self.args = args
        self.logger = logger
        self.llm = setup_llm(llmModel=args.llmModel, llmApiEndpoint=args.llmApiEndpoint, output_format=args.format)

        graph = StateGraph(Dict[str, Any])

        graph.add_node("llm", RunnableLambda(self.llm_node))
        graph.add_edge("llm", END)
        graph.set_entry_point("llm")
        self.compiled_graph = graph.compile()

    def llm_node(self, state):
        user_input = state["input"]
        system_message = SystemMessage(content="""
Break down the content provided by the user into:
1. Code-generation requirements
2. Test-generation requirements

Output a JSON string with elements: 'codeGenerationRequirements' and 'testGenerationRequirements'. Do not include any markdown                                 
"""                                
        )
        output = {
            "llm_output": self.llm.invoke([
                system_message,
                HumanMessage(content=user_input)
            ])
        }
        return output

    def handle_question(self, user_query, name):
        result = self.compiled_graph.invoke({"input": user_query})
        return result

