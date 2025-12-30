#!/bin/bash

# Initialize Ollama with required models for Liver Fibrosis Grading System

set -e

OLLAMA_HOST=${OLLAMA_HOST:-http://localhost:11434}

echo "Waiting for Ollama to be ready..."
while ! curl -s "${OLLAMA_HOST}/api/tags" > /dev/null; do
    echo "Ollama not ready, waiting..."
    sleep 2
done

echo "Ollama is ready!"

# Check if qwen2.5:14b-instruct model is available
if ! curl -s "${OLLAMA_HOST}/api/tags" | grep -q "qwen2.5:14b-instruct"; then
    echo "Pulling qwen2.5:14b-instruct model..."
    curl -X POST "${OLLAMA_HOST}/api/pull" -d '{"name": "qwen2.5:14b-instruct"}'
    echo "Model pulled successfully!"
else
    echo "qwen2.5:14b-instruct model already available"
fi

echo "Ollama initialization complete!"
