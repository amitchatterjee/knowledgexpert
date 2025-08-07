import os
import argparse
from transformers import AutoTokenizer, AutoModel

def download_model(model_path, model_name):
    if not os.path.exists(model_path):
        os.makedirs(model_path)
    tokenizer = AutoTokenizer.from_pretrained(model_name)
    model = AutoModel.from_pretrained(model_name)
    model.save_pretrained(model_path)
    tokenizer.save_pretrained(model_path)

def init_args():
    parser = argparse.ArgumentParser(description="Download and save HuggingFace model and tokenizer.")
    parser.add_argument('--modelPath', type=str, required=True, help='Directory to save the model and tokenizer')
    parser.add_argument('--modelName', type=str, required=True, help='HuggingFace model name (e.g., BAAI/bge-base-en-v1.5)')
    args = parser.parse_args()
    return args

if __name__ == "__main__":
    args = init_args()
    download_model(args.modelPath, args.modelName)
