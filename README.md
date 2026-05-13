# Knowledgexpert README
A companion project for Knowledgenet that helps developers build rules-based application using AI

## Development Environment Setup (One-time)

### Creating a Virtual Environment
Create a new Python virtual environment named `ai-venv` under your home directory:

```bash
cd ~
python3.14 -m venv ai-venv
```

### Activate the Virtual Environment
Add the following line to your `~/.bashrc` file:
```bash
echo 'source ~/ai-venv/bin/activate' >> ~/.bashrc
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
export EMBEDDING_MODEL_DATA=bge-m3
export EMBEDDING_MODEL_CODE=bge-m3

# handle self-signed certs
export NODE_TLS_REJECT_UNAUTHORIZED=0

# Apply the changes immediately
source ~/.bashrc
```

### Install pre-requisite software
```bash
pip install --upgrade pip
pip install -r $KNOWLEDGEXPERT_HOME/requirements.txt

# Required for looking into checkpointer
sudo dnf install sqlite
```

### Build Docker containers

#### Docker container for opensearch
Build the opensearch image using Docker Compose (uses `infrastructure/docker/opensearch-mcp/Dockerfile`):

```bash
docker compose -f $KNOWLEDGEXPERT_HOME/infrastructure/docker/docker-compose.yml build opensearch
```

#### Docker container for knowledgexpert base image
The image is intended for reuse across multiple MCP services.

```bash
docker compose -f $KNOWLEDGEXPERT_HOME/infrastructure/docker/docker-compose.yml build knowledgexpert-base
```

#### Docker container for linux-exec-mcp
The Linux Exec MCP service exposes a FastMCP tool named `ShellCommandExecutor` that validates and executes allowed shell commands from the configured working directory, returning `stdout`, `stderr`, and the command exit code.

```bash
docker compose -f $KNOWLEDGEXPERT_HOME/infrastructure/docker/docker-compose.yml build linux-exec-mcp
```

#### Setup the models, etc.
Pull the latest models, etc. periodically as shown below:

```bash
docker exec -it ollama ollama pull gemma4:latest
docker exec -it ollama ollama pull bge-m3
```

#### Configure parameters symlink
```bash
ln -s $KNOWLEDGEXPERT_HOME/infrastructure/conf $HOME/.knowledgexpert/conf
```

## Bring infrastructure components up and initialize Knowledge stores

### Bring up the infrastructure services

```bash
# Start services
docker compose -p '' -f $KNOWLEDGEXPERT_HOME/infrastructure/docker/docker-compose.yml up -d
```

### Build the vector/graph knowledge stores

```bash

# Graph store
python $KNOWLEDGEXPERT_HOME/src/graph_store.py --srcDirs \
    "$KNOWLEDGENET_HOME/src:knowledgenet" \
    "$KNOWLEDGENET_EX_HOME/autoins/src:autoins*" \
    --neo4jDatabase neo4j \
    --clear --store

# Know-it-all expert vector store
python $KNOWLEDGEXPERT_HOME/src/vector_store.py --collectionName 'all_collection' --documents  \
    "$KNOWLEDGENET_HOME/src;knowledgenet/*.py;class:code,subclass:platform" \
    "$KNOWLEDGENET_HOME/doc;;class:documentation,subclass:platform" \
    "$KNOWLEDGENET_EX_HOME/autoins/rules;;class:code,subclass:application,category:rules" \
    "$KNOWLEDGENET_EX_HOME/autoins/src/autoins;;class:code,subclass:application,category:application" \
    "$KNOWLEDGENET_EX_HOME/autoins/doc;;class:documentation,subclass:application,category:application" \
    --embeddingProvider ollama --embeddingApiUrl "http://localhost:11434" --embeddingModel "$EMBEDDING_MODEL_DATA" \
    --clear --store --chunkSize 4800 --chunkOverlap 720

# Wolfpack vector stores
python $KNOWLEDGEXPERT_HOME/src/vector_store.py --collectionName 'app_platform_collection' --documents  \
    "$KNOWLEDGENET_EX_HOME/autoins/src/autoins;entities.py,util.py;class:code,subclass:application,category:application" \
    --embeddingApiUrl "https://api.openai.com/v1/embeddings"  --embeddingModel "$EMBEDDING_MODEL_CODE" --embeddingProvider 'openai' \
    --clear --store --chunkSize 4800 --chunkOverlap 720

python $KNOWLEDGEXPERT_HOME/src/vector_store.py --collectionName 'rules_collection'  --documents \
    "$KNOWLEDGENET_EX_HOME/autoins/rules;;class:code,subclass:application,category:rules" \
    --embeddingApiUrl "https://api.openai.com/v1/embeddings" --embeddingModel "$EMBEDDING_MODEL_CODE" --embeddingProvider 'openai' \
    --clear --store --chunkSize 4800 --chunkOverlap 720

python $KNOWLEDGEXPERT_HOME/src/vector_store.py --collectionName 'app_docs_collection'  --documents \
    "$KNOWLEDGENET_EX_HOME/autoins/doc;;class:documentation,subclass:application,category:application" \
    --embeddingProvider ollama --embeddingApiUrl "http://localhost:11434" --embeddingModel "$EMBEDDING_MODEL_DATA" --clear --store \
    --chunkSize 4800 --chunkOverlap 720

python $KNOWLEDGEXPERT_HOME/src/vector_store.py --collectionName 'framework_docs_collection' --documents \
    "$KNOWLEDGENET_HOME/doc;;class:documentation,subclass:platform" \
    --embeddingProvider ollama --embeddingApiUrl "http://localhost:11434" --embeddingModel "$EMBEDDING_MODEL_DATA" \
    --clear --store --chunkSize 4800 --chunkOverlap 720
```

#### Query the vector database
```bash
python $KNOWLEDGEXPERT_HOME/src/vector_query.py --embeddingProvider ollama --embeddingApiUrl "http://localhost:11434" --embeddingModel "$EMBEDDING_MODEL_DATA" --collectionName 'all_collection'

python $KNOWLEDGEXPERT_HOME/src/vector_query.py --embeddingApiUrl "https://api.openai.com/v1/embeddings" --embeddingModel "$EMBEDDING_MODEL_CODE" --embeddingProvider 'openai' --collectionName 'rules_collection'

```

### Setup opensearch MCP knowledge stores

```bash
# get available plugins
curl -X GET 'https://localhost:9200/_cat/plugins?v' --insecure -u 'admin:openSearch$2025'

# get cluster settings
curl -X GET "https://localhost:9200/_cluster/settings" -u 'admin:openSearch$2025' --insecure

# create agents
curl --insecure \
  -H "Content-Type: application/x-ndjson" \
  --data-binary @"$KNOWLEDGEXPERT_HOME/infrastructure/conf/mcp/opensearch/agent.ndjson" \
  "https://localhost:9200/_plugins/_ml/agents/_register" \
  -u 'admin:openSearch$2025'

# register tools
curl -X POST 'https://localhost:9200/_plugins/_ml/mcp/tools/_register' \
  --insecure \
  -u 'admin:openSearch$2025' \
  -H 'Content-Type: application/json' \
  --data-binary @"$KNOWLEDGEXPERT_HOME/infrastructure/conf/mcp/opensearch/mcp-tools.json"

# Load msrp data
curl -sS -H "Content-Type: application/x-ndjson" \
  -u 'admin:openSearch$2025' \
  --data-binary @"$KNOWLEDGEXPERT_HOME/data/opensearch/msrp/toyota-2025-msrp-bulk.ndjson" \
  --insecure \
  "https://localhost:9200/_bulk"


curl -k -X PUT "https://localhost:9200/msrp/_mapping" \
  -H "Content-Type: application/json" \
  -H "Authorization: Basic YWRtaW46b3BlblNlYXJjaCQyMDI1" \
  --data-binary @"$KNOWLEDGEXPERT_HOME/data/opensearch/msrp/msrp-mappings.json"

```

## Execute Raven CLI

```bash
################################################
# Execute Raven using command line arguments:
###############################################
# Use openai/gpt5 model. Utilize Opensearch MCP client
python $KNOWLEDGEXPERT_HOME/src/raven_cli.py --checkpointerDir $HOME/.knowledgexpert/history --llmApiEndpoint "https://api.openai.com/v1/" --llmModel "gpt-5.4" --embeddingProvider ollama --embeddingApiUrl "http://localhost:11434" --embeddingModel "$EMBEDDING_MODEL_DATA" --mcpConfig $KNOWLEDGEXPERT_HOME/infrastructure/conf/raven/mcp.json --mcpInsecure --outputType 'knowledgexpert.raven.Answer' --input "What is the MSRP value for Toyota Prius 2025 base model?"

# Use openai/gpt5 model. Utilize agenticRag
python $KNOWLEDGEXPERT_HOME/src/raven_cli.py --checkpointerDir $HOME/.knowledgexpert/history --llmApiEndpoint "https://api.openai.com/v1/" --llmModel "gpt-5.4" --mcpConfig $KNOWLEDGEXPERT_HOME/infrastructure/conf/raven/mcp.json --mcpInsecure --embeddingProvider ollama --embeddingApiUrl "http://localhost:11434" --embeddingModel "$EMBEDDING_MODEL_DATA" --outputType 'knowledgexpert.raven.Answer'  --input "What is a ruleset?"

# Use openai/gpt5 model. Utilize linux-exec MCP client
python $KNOWLEDGEXPERT_HOME/src/raven_cli.py --checkpointerDir $HOME/.knowledgexpert/history --llmApiEndpoint "https://api.openai.com/v1/" --llmModel "gpt-5.4" --mcpConfig $KNOWLEDGEXPERT_HOME/infrastructure/conf/raven/mcp.json --mcpInsecure --embeddingProvider ollama --embeddingApiUrl "http://localhost:11434" --embeddingModel "$EMBEDDING_MODEL_DATA" --outputType 'knowledgexpert.raven.Answer'  --input "What is the minimum liability insurance required by the state of North Carolina for a driver's license?"


# Use anthropic claude as the llm with MCP
python $KNOWLEDGEXPERT_HOME/src/raven_cli.py --checkpointerDir $HOME/.knowledgexpert/history --embeddingProvider ollama --embeddingApiUrl "http://localhost:11434" --embeddingModel "$EMBEDDING_MODEL_DATA" --llmApiEndpoint "https://api.anthropic.com" --llmModel 'anthropic:claude-sonnet-4-20250514' --mcpConfig $KNOWLEDGEXPERT_HOME/infrastructure/conf/raven/mcp.json --mcpInsecure

# Use gemma as general llm running on ollama. There is no cost to use it but it is slooooow.
python $KNOWLEDGEXPERT_HOME/src/raven_cli.py --checkpointerDir $HOME/.knowledgexpert/history  --embeddingProvider ollama --embeddingApiUrl "http://localhost:11434" --embeddingModel "$EMBEDDING_MODEL_DATA" --llmApiEndpoint "http://localhost:11434" --llmModel "ollama:gemma4:latest" --mcpConfig $KNOWLEDGEXPERT_HOME/infrastructure/conf/raven/mcp.json --mcpInsecure --reactLoopMax 100

################################################
# Load command line params from a config file:
###############################################
python $KNOWLEDGEXPERT_HOME/src/raven_cli.py --checkpointerDir $HOME/.knowledgexpert/history --confDir $KNOWLEDGEXPERT_HOME/infrastructure/conf/wolfpack/analyst --outputType 'knowledgexpert.structures.AnalystOutput'


# This example demonstrates how to use --interactions to pass information from one expert to another
python $KNOWLEDGEXPERT_HOME/src/raven_cli.py --confDir $KNOWLEDGEXPERT_HOME/infrastructure/conf/wolfpack/developer --outputType 'knowledgexpert.structures.CodingOutput' --input "$(cat << 'EOF'
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

## Execute Wolfpack CLI
```bash

python $KNOWLEDGEXPERT_HOME/src/wolfpack_cli.py

# Start with an initial request read from a file
python $KNOWLEDGEXPERT_HOME/src/wolfpack_cli.py --requestPath $KNOWLEDGEXPERT_HOME/benchmark/wolfpack/prompt-1.txt

```

## Execute Knowledgexpert API for VS Code
```bash
uvicorn copilot_api:app --host 0.0.0.0 --port 9001 --app-dir "$KNOWLEDGEXPERT_HOME/src" --log-config ~/.knowledgexpert/conf/log-config.yaml

```

## Execute Wolfpack MCP
```bash
fastmcp run "$KNOWLEDGEXPERT_HOME/src/wolfpack_mcp.py" --transport http --port 9901 --host 0.0.0.0 --log-level INFO --

# For debugging/inspection, etc.
fastmcp dev "$KNOWLEDGEXPERT_HOME/src/wolfpack_mcp.py"

# The above command will open a browser and display the inspector. Connect using STDIO transport.

```

## List the available models on openai
```bash
# Openai
curl -s https://api.openai.com/v1/models -H "Authorization: Bearer $OPENAI_API_KEY" | jq

```

## Checkpointer inspection and debugging
```bash
sqlite3 ~/.knowledgexpert/history/checkpointer.sqlite

# List tables
.tables

# View checkpoints table schema
.schema checkpoints

# View result in CSV/Json format
.header on
.mode csv

.mode json

# Query
select * from checkpoints limit 1;

# Clear checkpoints
delete from checkpoints;

# Quit
.quit

```