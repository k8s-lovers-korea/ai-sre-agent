# SRE Agent Configuration Examples

This directory contains example configuration files for the SRE Agent.

## Files

- `agents.yaml` - Agent configurations and behavior settings
- `tools.yaml` - Tool configurations and permissions
- `guards.yaml` - Safety guard rules and policies
- `llm.yaml` - LLM provider settings and API configurations

## Usage

Copy these files to your deployment environment and customize as needed:

```bash
cp configs/agents.yaml.example /path/to/deployment/configs/agents.yaml
# Edit the file with your specific settings
```

## Environment Variables

Configuration can be overridden using environment variables:

- `SRE_AGENT_CONFIG_PATH` - Path to configuration directory
- `AZURE_OPENAI_ENDPOINT` - Azure OpenAI API endpoint
- `AZURE_OPENAI_API_KEY` - Azure OpenAI API key
- `K8S_NAMESPACE` - Default Kubernetes namespace
