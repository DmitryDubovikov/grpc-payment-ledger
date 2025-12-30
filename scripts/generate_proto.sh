#!/bin/bash
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

PROTO_DIR="$PROJECT_ROOT/proto"
OUTPUT_DIR="$PROJECT_ROOT/src/payment_service/proto"

mkdir -p "$OUTPUT_DIR/payment/v1"

touch "$OUTPUT_DIR/__init__.py"
touch "$OUTPUT_DIR/payment/__init__.py"
touch "$OUTPUT_DIR/payment/v1/__init__.py"

cd "$PROJECT_ROOT"

uv run python -m grpc_tools.protoc \
    --proto_path="$PROTO_DIR" \
    --python_out="$OUTPUT_DIR" \
    --pyi_out="$OUTPUT_DIR" \
    --grpc_python_out="$OUTPUT_DIR" \
    "$PROTO_DIR/payment/v1/payment.proto"

# Fix import paths in generated files (from payment.v1 -> payment_service.proto.payment.v1)
find "$OUTPUT_DIR" -name "*.py" -exec sed -i '' 's/^from payment\./from payment_service.proto.payment./' {} \; 2>/dev/null || \
    find "$OUTPUT_DIR" -name "*.py" -exec sed -i 's/^from payment\./from payment_service.proto.payment./' {} \;

echo "Proto files generated successfully in $OUTPUT_DIR"
