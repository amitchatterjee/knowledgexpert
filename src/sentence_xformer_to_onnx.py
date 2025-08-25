# requires sentence_transformers>=3.2.0
import argparse
from sentence_transformers import SentenceTransformer, export_optimized_onnx_model, export_dynamic_quantized_onnx_model
import os

def main(args):
    model_id = args.modelId
    output_dir = args.outputDir
    backend = getattr(args, 'backend', 'onnx')

    if not os.path.exists(output_dir):
        os.makedirs(output_dir, exist_ok=True)

    model = SentenceTransformer(model_id, backend=backend, model_kwargs={"export": True} if backend == "onnx" else {})
    model.save_pretrained(output_dir)

    if backend == "onnx":
        for optimization_config in ["O1", "O2", "O3", "O4"]:
            export_optimized_onnx_model(
                model,
                optimization_config=optimization_config,
                model_name_or_path=output_dir,
            )

        for quantization_config in ['arm64', 'avx2', 'avx512', 'avx512_vnni']:
            export_dynamic_quantized_onnx_model(
                model,
                quantization_config=quantization_config,
                model_name_or_path=output_dir,
            )

    # For openvino, model is already saved above

def parse_args():
    parser = argparse.ArgumentParser(description="Export SentenceTransformer model to ONNX and OpenVINO formats.")
    parser.add_argument('--modelId', type=str, required=True, help='Model ID to export (e.g., mixedbread-ai/mxbai-embed-large-v1)')
    parser.add_argument('--outputDir', type=str, required=True, help='Directory to save exported models')
    parser.add_argument('--backend', type=str, choices=['onnx', 'openvino', 'pytorch'], default='onnx', help='Backend for SentenceTransformer (default: onnx)')
    args = parser.parse_args()
    return args

if __name__ == "__main__":
    args = parse_args()
    main(args)