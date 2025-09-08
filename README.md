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
#export EMBEDDING_MODEL=msmarco-MiniLM-L6-v3
export EMBEDDING_MODEL=BAAI/bge-m3
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
python $KNOWLEDGEXPERT_HOME/src/graph_store.py --srcDirs \
    "$KNOWLEDGENET_HOME/src:knowledgenet" \
    "$KNOWLEDGENET_EX_HOME/autoins/src:autoins*" \
    --neo4jDatabase neo4j \
    --clear --store

python $KNOWLEDGEXPERT_HOME/src/vector_store.py --documents \
    "$KNOWLEDGENET_HOME/src;knowledgenet/*.py;class:code,subclass:platform" \
    "$KNOWLEDGENET_HOME/doc;;class:documentation,subclass:platform" \
    "$KNOWLEDGENET_EX_HOME/autoins/rules;;class:code,subclass:application,category:rules" \
    "$KNOWLEDGENET_EX_HOME/autoins/src/autoins;;class:code,subclass:application,category:application" \
    "$KNOWLEDGENET_EX_HOME/autoins/doc;;class:documentation,subclass:application,category:application" \
    --embeddingApiUrl "http://localhost:9000" --embeddingModel "$EMBEDDING_MODEL" \
    --collectionName 'all_collection' --clear --store --chunkSize 4800 --chunkOverlap 720

python $KNOWLEDGEXPERT_HOME/src/vector_store.py --documents \
    "$KNOWLEDGENET_EX_HOME/autoins/doc;;class:documentation,subclass:application,category:application" \
    "$KNOWLEDGENET_EX_HOME/autoins/rules;;class:code,subclass:application,category:rules" \
    --embeddingApiUrl "http://localhost:9000" --embeddingModel "$EMBEDDING_MODEL" --clear --store \
    --collectionName 'analyst_collection' --chunkSize 4800 --chunkOverlap 720

python $KNOWLEDGEXPERT_HOME/src/vector_store.py --documents \
    "$KNOWLEDGENET_EX_HOME/autoins/rules;;class:code,subclass:application,category:rules" \
    --embeddingApiUrl "http://localhost:9000" --embeddingModel "$EMBEDDING_MODEL" \
    --collectionName 'rules_collection' --clear --store --chunkSize 4800 --chunkOverlap 720

python $KNOWLEDGEXPERT_HOME/src/vector_store.py --documents \
    "$KNOWLEDGENET_EX_HOME/autoins/doc;;class:documentation,subclass:application,category:application" \
    --embeddingApiUrl "http://localhost:9000" --embeddingModel "$EMBEDDING_MODEL" --clear --store \
    --collectionName 'app_docs_collection' --chunkSize 4800 --chunkOverlap 720

python $KNOWLEDGEXPERT_HOME/src/vector_store.py --documents \
    "$KNOWLEDGENET_HOME/doc;;class:documentation,subclass:platform" \
    --embeddingApiUrl "http://localhost:9000" --embeddingModel "$EMBEDDING_MODEL" \
    --collectionName 'framework_docs_collection' --clear --store --chunkSize 4800 --chunkOverlap 720
```

## Execute Knowledgexpert cli
```bash
# Use codellama as the graph llm and gemma as general llm running on ollama. There is no cost to use it but it is slooooow.
python $KNOWLEDGEXPERT_HOME/src/expert_cli.py --embeddingApiUrl "http://localhost:9000" --embeddingModel "$EMBEDDING_MODEL" --llmApiEndpoint "http://localhost:11434" --llmModel "ollama:gemma:latest" --useGraphRag --graphLlmApiEndpoint http://localhost:11434  --graphLlmModel 'ollama:codellama:latest'

# Use anthropic claude as the graph llm and the general llm
python $KNOWLEDGEXPERT_HOME/src/expert_cli.py --embeddingApiUrl "http://localhost:9000" --embeddingModel "$EMBEDDING_MODEL" --llmApiEndpoint "https://api.anthropic.com" --llmModel 'anthropic:claude-sonnet-4-20250514' --useGraphRag --graphLlmApiEndpoint "https://api.anthropic.com"  --graphLlmModel 'anthropic:claude-sonnet-4-20250514'

# Use anthropic claude as the graph llm and gpt4.1-mini as general llm
python $KNOWLEDGEXPERT_HOME/src/expert_cli.py --embeddingApiUrl "http://localhost:9000" --embeddingModel "$EMBEDDING_MODEL" --llmApiEndpoint "https://api.openai.com/v1/" --llmModel "gpt-4.1-mini" --useGraphRag --graphLlmApiEndpoint "https://api.anthropic.com" --graphLlmModel 'anthropic:claude-sonnet-4-20250514'


# Load command line params from a config file:
python $KNOWLEDGEXPERT_HOME/src/expert_cli.py --confDir $KNOWLEDGEXPERT_HOME/infrastructure/conf/deep-expert/analyst --structureClass 'knowledgexpert.structures.AnalystOutput'

```

## Execute Deepxpert CLI
```bash

python $KNOWLEDGEXPERT_HOME/src/deepxpert_cli.py 

```

## Execute Knowledgexpert API
```bash
uvicorn copilot_api:app --host 0.0.0.0 --port 9001 --app-dir "$KNOWLEDGEXPERT_HOME/src"
```

## Query the vector database
```bash
python $KNOWLEDGEXPERT_HOME/src/vector_query.py --embeddingApiUrl "http://localhost:9000" --embeddingModel "$EMBEDDING_MODEL"
```
## List the available models
```bash
# Openai
curl -s https://api.openai.com/v1/models -H "Authorization: Bearer $OPENAI_API_KEY" | jq

```