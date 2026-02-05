#!/bin/bash

# Ensure we act on the correct directory
cd "$(dirname "$0")"

# Define the prompt for the agent
PROMPT="Use the MCP server to boot the board defined in vcu118_daq3.yaml using the BootFabric strategy. Wait for the boot to complete and then retrieve the 'dmesg' log."

echo "Starting MCP BootFabric Test..."
echo "Target Directory: $(pwd)"
echo "Prompt: $PROMPT"

# Check if gemini command exists
if ! command -v gemini &> /dev/null; then
    echo "Error: 'gemini' command not found. Please ensure the Gemini CLI is installed and in your PATH."
    exit 1
fi

# Invoke gemini
echo "Invoking Gemini..."
gemini "$PROMPT" --context "$(pwd)"

echo "Test execution finished."
