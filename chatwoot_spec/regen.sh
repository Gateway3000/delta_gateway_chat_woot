#!/bin/bash
set -euo pipefail

# === CONFIG ===
SWAGGER_URL="https://www.chatwoot.com/developers/swagger.json"
SPEC_DIR="chatwoot_spec"
CONFIG_PATH="$SPEC_DIR/config.yaml"

# === MAIN PIPELINE ===
echo "🚀 Deleting previous OpenAPI spec..."
# shellcheck disable=SC2115
rm -rf "./chatwoot_client"
rm -f "$SPEC_DIR/chatwoot_client_README.md"
rm -f "$SPEC_DIR/swagger.json"

echo "🌐 Downloading Swagger spec..."
curl -sSL "$SWAGGER_URL" -o "$SPEC_DIR/swagger.json"

echo "🔄 Generating Python client from Swagger..."
openapi-generator-cli generate \
  -i "$SPEC_DIR/swagger.json" \
  -c "$CONFIG_PATH" \
  -g python \
  -o "$SPEC_DIR"

# === MOVE chatwoot_client TO ROOT ===
echo "🚚 Moving chatwoot_client package to root..."
mv "$SPEC_DIR/chatwoot_client" "./chatwoot_client"

# === REMOVE unnessesary files and packages ===
echo "🧹 Removing files and packages..."
rm -rf "$SPEC_DIR/chatwoot_client"
rm -rf "$SPEC_DIR/.openapi-generator"
rm -f "$SPEC_DIR/.openapi-generator-ignore"

# === RUFF CLEANUP ===
echo "🧹 Running Ruff cleanup..."
ruff check "$SPEC_DIR" "./chatwoot_client" --ignore E721 --fix
ruff format "$SPEC_DIR" "./chatwoot_client"

echo "✅ Ruff cleanup done!"
echo "🎉 Client successfully regenerated and cleaned!"
