import argparse
import logging
import os
import sys

from knowledgexpert.raven import Answer, Raven

def parse_args():
    parser = argparse.ArgumentParser(description="Raven CLI")
    parser.add_argument("--llmModel", help="LLM model identifier")
    parser.add_argument("--llmApiEndpoint", default=None, help="LLM API endpoint")
    parser.add_argument("--format", choices=["raw", "structured"], default="structured", help="Output format: 'raw' or 'structured'")
    parser.add_argument("--mcpConfig", required=True, help="Path to MCP config JSON")
    parser.add_argument("--mcpInsecure", action="store_true", help="Disable TLS verification for MCP")
    parser.add_argument("--input", required=True, help="Input text to invoke the agent with")
    parser.add_argument("--promptDir", default=os.path.join(os.path.expanduser("~"), ".knowledgexpert", "conf", "raven"), help="Directory containing prompt templates (default: ~/.knowledgexpert/conf/prompt)")
    args = parser.parse_args()
    return args

if __name__ == "__main__":
    args = parse_args()

    logger = logging.getLogger("Raven driver")
    logger.setLevel(logging.DEBUG)
    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter("%(levelname)s: %(message)s"))
    logger.addHandler(handler)

    try:
        raven = Raven(
            logger,
            structure=Answer,
            llmModel=args.llmModel,
            llmApiEndpoint=args.llmApiEndpoint,
            format=args.format,
            mcpConfig=args.mcpConfig,
            mcpInsecure=args.mcpInsecure,
            promptDir=args.promptDir
        )

        input = {"messages": [{"role": "user", "content": args.input}]}

        result = raven.invoke(input)

        print("Agent result:")
        print(result)

    except Exception as e:
        logger.exception("Failed to run Raven: %s", e)
        sys.exit(1)
