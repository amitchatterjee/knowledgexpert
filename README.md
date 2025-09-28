# Knowledgexpert README
A companion project for Knowledgenet that helps developers build rules-based application using AI

## Development Environment Setup (One-time)

### Creating a Virtual Environment
Create a new Python virtual environment named `ai-venv` under your home directory:

```bash
cd ~
python3.13 -m venv ai-venv
```

### Activate the Virtual Environment
Add the following line to your `~/.bashrc` file:
```bash
echo 'source ~/ai-venv/bin/activate' >> ~/.bashrc
```

The virtual environment will now automatically activate when you open a new terminal.
### Verification

Verify the virtual environment is active by checking Python's location:
```bash
which python
# Should output: ~/ai-venv/bin/python
```

### Add the necessary environment variables to ~/.bashrc
```bash
# Change as needed
export KNOWLEDGEXPERT_HOME=$GIT_HOME/git/knowledgexpert
export KNOWLEDGEXPERT_VSCODE_HOME=$GIT_HOME/git/knowledgexpert-vscode
export HF_TOKEN=<huggingface_token>
export ANTHROPIC_API_KEY=<anthropic_api_key>
export OPENAI_API_KEY=<openai_key>
#export EMBEDDING_MODEL_DATA=msmarco-MiniLM-L6-v3
export EMBEDDING_MODEL_DATA=BAAI/bge-m3
export EMBEDDING_MODEL_CODE=BAAI/bge-m3
# Apply the changes immediately
source ~/.bashrc
```

### Install pre-requisite software
```bash   
pip install -r $KNOWLEDGEXPERT_HOME/requirements.txt
```

## Setup the infrastructure components needed for this service

### Setup the models, etc.
```bash
docker exec -it ollama ollama pull deepseek-r1
docker exec -it ollama ollama pull gemma:latest
docker exec -it ollama ollama pull mistral:latest
docker exec -it ollama ollama pull codellama:latest
# To run and test (not needed, if accessing from langchain)
docker exec -it ollama ollama run deepseek-r1
```

### Install embeddings models locally (**Experimental)
TODO

### Configure parameters
```bash
ln -s $KNOWLEDGEXPERT_HOME/infrastructure/conf $HOME/.knowledgexpert/conf
```

## Bring up Servers
This is needed to load the knowledge base and to run the experts.

```bash
docker compose -p '' -f $KNOWLEDGEXPERT_HOME/infrastructure/docker/docker-compose.yml up -d
```

## Build the knowledge base
Run the following commands:
```bash

# Graph store
python $KNOWLEDGEXPERT_HOME/src/graph_store.py --srcDirs \
    "$KNOWLEDGENET_HOME/src:knowledgenet" \
    "$KNOWLEDGENET_EX_HOME/autoins/src:autoins*" \
    --neo4jDatabase neo4j \
    --clear --store

# Know-it-all expert vector store
python $KNOWLEDGEXPERT_HOME/src/vector_store.py --documents \
    "$KNOWLEDGENET_HOME/src;knowledgenet/*.py;class:code,subclass:platform" \
    "$KNOWLEDGENET_HOME/doc;;class:documentation,subclass:platform" \
    "$KNOWLEDGENET_EX_HOME/autoins/rules;;class:code,subclass:application,category:rules" \
    "$KNOWLEDGENET_EX_HOME/autoins/src/autoins;;class:code,subclass:application,category:application" \
    "$KNOWLEDGENET_EX_HOME/autoins/doc;;class:documentation,subclass:application,category:application" \
    --embeddingApiUrl "http://localhost:9000" --embeddingModel "$EMBEDDING_MODEL_DATA" \
    --collectionName 'all_collection' --clear --store --chunkSize 4800 --chunkOverlap 720

# DeepXpert vector stores
python $KNOWLEDGEXPERT_HOME/src/vector_store.py --documents \
    "$KNOWLEDGENET_EX_HOME/autoins/src/autoins;entities.py,util.py;class:code,subclass:application,category:application" \
    --embeddingApiUrl "https://api.openai.com/v1/embeddings"  --embeddingModel "$EMBEDDING_MODEL_CODE" --embeddingProvider 'openai' \
    --collectionName 'app_platform_collection' --clear --store --chunkSize 4800 --chunkOverlap 720

python $KNOWLEDGEXPERT_HOME/src/vector_store.py --documents \
    "$KNOWLEDGENET_EX_HOME/autoins/rules;;class:code,subclass:application,category:rules" \
    --embeddingApiUrl "https://api.openai.com/v1/embeddings" --embeddingModel "$EMBEDDING_MODEL_CODE" --embeddingProvider 'openai' \
    --collectionName 'rules_collection' --clear --store --chunkSize 4800 --chunkOverlap 720

python $KNOWLEDGEXPERT_HOME/src/vector_store.py --documents \
    "$KNOWLEDGENET_EX_HOME/autoins/doc;;class:documentation,subclass:application,category:application" \
    --embeddingApiUrl "http://localhost:9000" --embeddingModel "$EMBEDDING_MODEL_DATA" --clear --store \
    --collectionName 'app_docs_collection' --chunkSize 4800 --chunkOverlap 720

python $KNOWLEDGEXPERT_HOME/src/vector_store.py --documents \
    "$KNOWLEDGENET_HOME/doc;;class:documentation,subclass:platform" \
    --embeddingApiUrl "http://localhost:9000" --embeddingModel "$EMBEDDING_MODEL_DATA" \
    --collectionName 'framework_docs_collection' --clear --store --chunkSize 4800 --chunkOverlap 720

```

## Query the vector database
```bash
python $KNOWLEDGEXPERT_HOME/src/vector_query.py --embeddingApiUrl "http://localhost:9000" --embeddingModel "$EMBEDDING_MODEL_DATA" --collectionName 'all_collection'

python $KNOWLEDGEXPERT_HOME/src/vector_query.py --embeddingApiUrl "https://api.openai.com/v1/embeddings" --embeddingModel "$EMBEDDING_MODEL_CODE" --embeddingProvider 'openai' --collectionName 'rules_collection'

```

## Execute Knowledgexpert cli
```bash
################################################
# Execute expert using command line arguments:
###############################################
# Use codellama as the graph llm and gemma as general llm running on ollama. There is no cost to use it but it is slooooow.
python $KNOWLEDGEXPERT_HOME/src/expert_cli.py --embeddingApiUrl "http://localhost:9000" --embeddingModel "$EMBEDDING_MODEL_DATA" --llmApiEndpoint "http://localhost:11434" --llmModel "ollama:gemma:latest" --useGraphRag --graphLlmApiEndpoint http://localhost:11434  --graphLlmModel 'ollama:codellama:latest'

# Use anthropic claude as the graph llm and the general llm
python $KNOWLEDGEXPERT_HOME/src/expert_cli.py --embeddingApiUrl "http://localhost:9000" --embeddingModel "$EMBEDDING_MODEL_DATA" --llmApiEndpoint "https://api.anthropic.com" --llmModel 'anthropic:claude-sonnet-4-20250514' --useGraphRag --graphLlmApiEndpoint "https://api.anthropic.com"  --graphLlmModel 'anthropic:claude-sonnet-4-20250514'

# Use anthropic claude as the graph llm and gpt4.1-mini as general llm
python $KNOWLEDGEXPERT_HOME/src/expert_cli.py --embeddingApiUrl "http://localhost:9000" --embeddingModel "$EMBEDDING_MODEL_DATA" --llmApiEndpoint "https://api.openai.com/v1/" --llmModel "gpt-4.1-mini" --useGraphRag --graphLlmApiEndpoint "https://api.anthropic.com" --graphLlmModel 'anthropic:claude-sonnet-4-20250514'

################################################
# Load command line params from a config file:
###############################################
python $KNOWLEDGEXPERT_HOME/src/expert_cli.py --confDir $KNOWLEDGEXPERT_HOME/infrastructure/conf/expert --structureClass 'knowledgexpert.structures.CodingOutput'

python $KNOWLEDGEXPERT_HOME/src/expert_cli.py --confDir $KNOWLEDGEXPERT_HOME/infrastructure/conf/deep-expert/analyst --structureClass 'knowledgexpert.structures.AnalystOutput'

# This example demonstrates how to use --interactions to pass information from one expert to another
python $KNOWLEDGEXPERT_HOME/src/expert_cli.py --confDir $KNOWLEDGEXPERT_HOME/infrastructure/conf/deep-expert/developer --structureClass 'knowledgexpert.structures.CodingOutput' --interactions "$(cat << EOF
Analysis:
   This is a contract validation rule that enforces age restrictions for insurance claims. The rule needs to:
   1. Access the ExecutionContext to get driver information
   2. Calculate the driver's age using their date of birth (dob attribute from Driver class)
   3. Read the minimum_age configuration parameter from the ruleset_context
   4. Compare the calculated age against the minimum threshold
   5. Create an Action fact with appropriate denial parameters when the driver is underage.
   
   The rule should follow the established pattern of other contract rules, using the 'contract-ruleset' named fact and the execute() utility function to determine if the rule should be evaluated. The age calculation will need to handle date arithmetic to compute the current age from the date of birth.\n\nSince this is a mandatory configuration parameter with no default values, the rule-config.json must be updated to include the minimum_age parameter in the contract ruleset configuration. The rule should fail gracefully if this parameter is missing, as it's a required configuration.
   
Code-generation Requirements:
   Rule function name: deny_underage_driver. The rule should use the @ruledef decorator and return a Rule object that matches ExecutionContext facts where the driver's computed age is below the minimum age threshold specified in the ruleset configuration.
EOF
)"

```

## Execute DeepXpert CLI
```bash

# Interactive
python $KNOWLEDGEXPERT_HOME/src/deepxpert_cli.py

python $KNOWLEDGEXPERT_HOME/src/deepxpert_cli.py --requestPath $KNOWLEDGEXPERT_HOME/benchmark/request/underage_rule_request.txt

```

## Execute Knowledgexpert API for VS Code
```bash
uvicorn copilot_api:app --host 0.0.0.0 --port 9001 --app-dir "$KNOWLEDGEXPERT_HOME/src" --log-config ~/.knowledgexpert/conf/log-config.yaml

```

## Execute DeepXpert MCP
```bash
fastmcp run "$KNOWLEDGEXPERT_HOME/src/deepxpert_mcp.py" --transport http --port 9901 --host 0.0.0.0 --log-level INFO --

# For debugging/inspection, etc.
fastmcp dev "$KNOWLEDGEXPERT_HOME/src/deepxpert_mcp.py"

# The above command will open a browser and display the inspector. Connect using STDIO transport.

```

## List the available models
```bash
# Openai
curl -s https://api.openai.com/v1/models -H "Authorization: Bearer $OPENAI_API_KEY" | jq

```