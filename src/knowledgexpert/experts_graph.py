from typing import Any, Dict
from langchain_core.messages import HumanMessage, SystemMessage
from langgraph.graph import StateGraph, END
from langchain_core.runnables import RunnableLambda

from knowledgexpert.util import setup_llm

class ExpertsGraph:
    def __init__(self, args, logger, coding_expert):
        self.args = args
        self.logger = logger
        self.coding_expert = coding_expert
        self.llm = setup_llm(llmModel=args.llmModel, llmApiEndpoint=args.llmApiEndpoint, output_format=args.format)

        graph = StateGraph(Dict[str, Any])

        graph.add_node("frontliner", RunnableLambda(self.frontliner_node))
        graph.add_edge("frontliner", END)
        graph.set_entry_point("frontliner")
        self.compiled_graph = graph.compile()

    def frontliner_node(self, state):
        user_input = state["input"]
        system_message = SystemMessage(content='''
            Break down the content provided by the user into:
            1. Summary.
            2. Classification of the request. Can have one of the following values: question, code-generation, configuration-generation, test-case generation.
            3. Code-generation requirements. Populate this only when the classification is code-generation.
            4. Configuration-generation requirements. Populate this only when the classification is configuration-generation.
            5. Test-generation requirements. Populate this only when the classification is code-generation or test-generation.
            6. Question: Populate this only when the classification is question.
            7. Analysis: Provide any additional information based on your analysis.

            Perform any editorial changes as needed. Do not generate any code or configuration. Output a JSON string as per the above fields. Do not include any markdown                                 
            '''                             
        )
        output = {
            "frontliner_output": self.llm.invoke([
                system_message,
                HumanMessage(content=user_input)
            ])
        }
        return output
    
    def coding_expert_node(self, state):

        return ""

    def handle_question(self, user_query, name):
        result = self.compiled_graph.invoke({"input": user_query})
        return result

