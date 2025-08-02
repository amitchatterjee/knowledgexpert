# Knowledgexpert README
A companion project for Knowledgenet that helps developers build rules-based application using AI

## Development environment setup

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

# Apply the changes immediately
source ~/.bashrc
```

### Install pre-requisite software
```bash   
pip install -r $KNOWLEDGEXPERT_HOME/requirements.txt
```

## Setup the infrastructure components needed for this service
### Bring up the docker containers.
```bash
docker compose -p '' -f $KNOWLEDGEXPERT_HOME/infrastructure/docker/docker-compose.yml up -d
```
### Setup the models, etc.
```bash
docker exec -it ollama ollama pull deepseek-r1
docker exec -it ollama ollama pull gemma:latest
docker exec -it ollama ollama pull mistral:latest
docker exec -it ollama ollama pull codellama:latest
# To run and test (not needed, if accessing from langchain)
docker exec -it ollama ollama run deepseek-r1
```

### Configure model and other params
```bash
ln -s $KNOWLEDGEXPERT_HOME/infrastructure/conf $HOME/.knowledgexpert/conf
```

## Build the Knowledgebase
1. Clone the repositories - knowledgenet and knowledgenet-examples
1. Set environment variables: KNOWLEDGENET_HOME and KNOWLEDGENET_EX_HOME. Add it to $HOME/.bashrc
1. Run the following commands:
```bash
python $KNOWLEDGEXPERT_HOME/src/graph_store.py --srcDirs $KNOWLEDGENET_HOME/src $KNOWLEDGENET_EX_HOME/autoins/src --clear --store

python $KNOWLEDGEXPERT_HOME/src/vector_store.py --documents "$KNOWLEDGENET_HOME/src;class:code,subclass:platform" "$KNOWLEDGENET_HOME/doc;class:documentation,subclass:platform" "$KNOWLEDGENET_EX_HOME/autoins/rules;class:code,subclass:application,category:rules" "$KNOWLEDGENET_EX_HOME/autoins/src/autoins;class:code,subclass:application,category:application" --embeddingApiUrl "http://localhost:8080" --embeddingModel 'msmarco-MiniLM-L-6-v3' --clear --store

python $KNOWLEDGEXPERT_HOME/src/vector_store.py --documents  "$KNOWLEDGENET_HOME/doc;class:documentation,subclass:platform" --embeddingApiUrl "http://localhost:8080" --embeddingModel 'msmarco-MiniLM-L-6-v3' --clear --store --collectionName 'documents_collection'
```

## Execute Knowledgexpert cli
```bash
# Use anthropic claude as the graph llm and deepseek (running on lambda.ai) as the general llm
python $KNOWLEDGEXPERT_HOME/src/expert_cli.py --embeddingApiUrl "http://localhost:8080" --embeddingModel 'msmarco-MiniLM-L-6-v3'  --llmApiEndpoint 'https://api.lambda.ai/v1' --llmModel 'openai:deepseek-r1-671b' --useGraphRag --graphLlmApiEndpoint 'https://api.anthropic.com'  --graphLlmModel 'anthropic:claude-sonnet-4-20250514'

# Use anthropic claude as the graph llm and llama (running on lambda.ai) as the general llm
python $KNOWLEDGEXPERT_HOME/src/expert_cli.py --embeddingApiUrl "http://localhost:8080" --embeddingModel 'msmarco-MiniLM-L-6-v3' --llmApiEndpoint 'https://api.lambda.ai/v1' --llmModel 'openai:llama-4-scout-17b-16e-instruct' --useGraphRag --graphLlmApiEndpoint https://api.anthropic.com  --graphLlmModel 'anthropic:claude-sonnet-4-20250514'

# Use codellama as the graph llm (running on ollama) and llama (running on lambda.ai) as the general llm
python $KNOWLEDGEXPERT_HOME/src/expert_cli.py --embeddingApiUrl "http://localhost:8080" --embeddingModel 'msmarco-MiniLM-L-6-v3' --llmApiEndpoint 'https://api.lambda.ai/v1' --llmModel 'openai:llama-4-scout-17b-16e-instruct' --useGraphRag --graphLlmApiEndpoint http://localhost:11434  --graphLlmModel 'ollama:codellama:latest'

# Use llama as the graph llm (running on lambda.ai) and llama (running on lambda.ai) as the general llm
python $KNOWLEDGEXPERT_HOME/src/expert_cli.py --embeddingApiUrl "http://localhost:8080" --embeddingModel 'msmarco-MiniLM-L-6-v3' --llmApiEndpoint 'https://api.lambda.ai/v1' --llmModel 'openai:llama-4-scout-17b-16e-instruct' --useGraphRag --graphLlmApiEndpoint 'https://api.lambda.ai/v1'  --graphLlmModel 'openai:llama-4-scout-17b-16e-instruct'

# Use anthropic claude as the graph llm and the general llm
python $KNOWLEDGEXPERT_HOME/src/expert_cli.py --embeddingApiUrl "http://localhost:8080" --embeddingModel 'msmarco-MiniLM-L-6-v3' --llmApiEndpoint "https://api.anthropic.com" --llmModel 'anthropic:claude-sonnet-4-20250514' --useGraphRag --graphLlmApiEndpoint "https://api.anthropic.com"  --graphLlmModel 'anthropic:claude-sonnet-4-20250514'
```

## Execute Knowledgexpert API
uvicorn copilot_api:app --host 0.0.0.0 --port 9000 --app-dir "$KNOWLEDGEXPERT_HOME/src"

## Query the vector database
```bash
python $KNOWLEDGEXPERT_HOME/src/vector_query.py --embeddingApiUrl "http://localhost:8080" --embeddingModel 'msmarco-MiniLM-L-6-v3'
```
