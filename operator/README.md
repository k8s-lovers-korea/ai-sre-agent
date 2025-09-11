# Kubernetes Operator

> Go-based Kubernetes operator that watches CRDs and delegates decision-making to the SRE Agent.

## Components

- **CRD Watcher**: Monitors Kubernetes resources and events
- **Agent Client**: Communicates with SRE Agent via HTTP API
- **Controller Logic**: Implements basic conditional checks before agent delegation

## API Endpoints (to SRE Agent)

- `POST /decide` - Request decision from LLM-based agent
- `POST /execute` - Execute approved actions

## Development

*To be implemented...*

```bash
# Future commands
go mod init k8s-sre-operator
go build -o bin/operator main.go
```
