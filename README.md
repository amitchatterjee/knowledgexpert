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
    pip install -r requirements.txt
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

## Execute Knowledgexpert

### Using CLI

### API service
