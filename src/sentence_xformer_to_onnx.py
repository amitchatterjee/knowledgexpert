# requires sentence_transformers>=3.2.0
import argparse
from sentence_transformers import SentenceTransformer, export_optimized_onnx_model, export_dynamic_quantized_onnx_model
import os

def main(args):
    model_id = args.modelId
    output_dir = args.outputDir

    if not os.path.exists(output_dir):
        os.makedirs(output_dir, exist_ok=True)

    onnx_model = SentenceTransformer(model_id, backend="onnx", model_kwargs={"export": True})
    onnx_model.save_pretrained(output_dir)

    for optimization_config in ["O1", "O2", "O3", "O4"]:
        export_optimized_onnx_model(
            onnx_model,
            optimization_config=optimization_config,
            model_name_or_path=output_dir,
        )

    for quantization_config in ['arm64', 'avx2', 'avx512', 'avx512_vnni']:
        export_dynamic_quantized_onnx_model(
            onnx_model,
            quantization_config=quantization_config,
            model_name_or_path=output_dir,
        )

    openvino_model = SentenceTransformer(model_id, backend="openvino")
    openvino_model.save_pretrained(output_dir)

def parse_args():
    parser = argparse.ArgumentParser(description="Export SentenceTransformer model to ONNX and OpenVINO formats.")
    parser.add_argument('--modelId', type=str, required=True, help='Model ID to export (e.g., mixedbread-ai/mxbai-embed-large-v1)')
    parser.add_argument('--outputDir', type=str, required=True, help='Directory to save exported models')
    args = parser.parse_args()
    return args

if __name__ == "__main__":
    args = parse_args()
    main(args)