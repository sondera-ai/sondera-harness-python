import os
import re
import subprocess
import sys
from pathlib import Path


def generate():
    setup_dir = Path(__file__).parent.parent
    proto_dir = setup_dir / "protos"
    output_dir = setup_dir / "src" / "sondera" / "proto"

    output_dir.mkdir(parents=True, exist_ok=True)

    proto_files = list(proto_dir.rglob("*.proto"))

    print(f"Generating code for {len(proto_files)} proto files...")

    command = [
        sys.executable,
        "-m",
        "grpc_tools.protoc",
        f"--proto_path={proto_dir}",
        f"--python_out={output_dir}",
        f"--grpc_python_out={output_dir}",
        f"--pyi_out={output_dir}",
    ] + [str(p) for p in proto_files]

    subprocess.run(command, check=True)

    # Convert absolute imports to relative
    for py_file in output_dir.rglob("*_pb2*.py"):
        content = py_file.read_text()
        # Regex to find 'from sondera.xxx import yyy_pb2'
        # and change to 'from ..xxx import yyy_pb2'
        content = re.sub(
            r"from sondera\.(.*) import (.*)_pb2", r"from ...\1 import \2_pb2", content
        )
        py_file.write_text(content)

    # 2. Ensure __init__.py files exist
    for root, _dirs, _files in os.walk(output_dir / "sondera"):
        root_path = Path(root)
        if not (root_path / "__init__.py").exists():
            (root_path / "__init__.py").touch()

    print("Successfully generated and patched protos.")


if __name__ == "__main__":
    generate()
