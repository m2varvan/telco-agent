# Telco Agent

Develop and evaluate an AI-powered **Network Incident Triage Assistant** that uses open-source AI models to help identify potential causes of network incidents.

The project explores how enterprise organizations can leverage open-source AI solutions by evaluating:

- Agent capabilities for incident analysis and troubleshooting
- Integration with enterprise data sources and tools
- Operational considerations
- Economic trade-offs of deploying open-source AI models

---

# Project Setup

## Prerequisites

Ensure you have:

- Python 3.12+
- A Python virtual environment
- NVIDIA API access for NIM models

Activate the virtual environment:

```bash
source .venv/bin/activate
```

---

# Setting Up NVIDIA NIM API Key

NVIDIA NIM provides access to hosted AI models through NVIDIA's API platform.

## 1. Generate an NVIDIA API Key

1. Go to:
   https://build.nvidia.com/nvidia

2. Create a developer account

3. Complete profile setup and phone verification

4. Navigate to:

```
Settings → API Keys
```

5. Generate an API key

6. Copy the key immediately.

> The key starts with `nvapi-` and is only displayed once.

---

## 2. Add API Key to `.env`

Create a file named `.env` in the project root:

```env
NVIDIA_API_KEY=nvapi-your-key-here
```

The `.env` file should not be committed to Git.

---

# Exploring Available NAT Components

NVIDIA NeMo Agent Toolkit (NAT) provides CLI commands for discovering available components registered in your local environment.

Components represent reusable building blocks used to create AI agents, including:

- LLM providers
- Agent functions/tools
- Retrievers
- Memory systems
- Tool integrations

## View Available Commands

```bash
nat info components --help
```

## Search Components by Category

Examples:

```bash
nat info components
```

List available functions:

```bash
nat info components --types function
```

List available tool wrappers:

```bash
nat info components --types tool_wrapper
```

List available retriever providers:

```bash
nat info components --types retriever_provider
```

List available LLM providers:

```bash
nat info components --types llm_provider
```

---

## Component Categories

| Component Type | Purpose |
|---|---|
| `llm_provider` | Integrations with hosted or local language models |
| `function` | Callable tools/functions an agent can execute |
| `tool_wrapper` | External tools exposed to agents |
| `retriever_provider` | Retrieval systems used for RAG workflows |
| `memory` | Components for storing conversation state |
| `embedder_provider` | Embedding model integrations |

---

## Export Component Metadata

Component information can be exported for easier searching:

```bash
nat info components -t llm_provider > llm_providers.txt
```

The output contains:

- Package name
- Version
- Component type
- Component name
- Description

The full component registry can be exported using:

```bash
nat info components > components.txt
```

`components.txt` contains all available NAT components. Use it as a reference when searching for available integrations.

---

# Workflow Configuration (`workflow.yml`)

The `workflow.yml` file defines how NAT components are assembled into a runnable agent.

NAT workflows are composed of reusable components such as:

- LLMs for reasoning
- Functions/tools for external actions
- Retrievers for knowledge retrieval
- Memory systems for maintaining state
- Agent workflows that define execution behavior

---

## Workflow Structure

Common top-level sections include:

| Section | Purpose |
|---|---|
| `llms` | Defines the language models used by the agent |
| `functions` | Registers tools the agent can call |
| `retrievers` | Configures retrieval systems for RAG |
| `embedders` | Defines embedding models for vector search |
| `memory` | Configures conversation memory |
| `workflow` | Defines the agent architecture and execution flow |

---

## Components and `_type`

Each component is instantiated using the `_type` field.

The `_type` value must match a registered NAT component.

Example:

```yaml
llms:
  telco_model:
    _type: azure_openai
```

Here:

- `telco_model` is the name used inside your workflow
- `_type: azure_openai` tells NAT which registered component to create

---

## Example Agent Workflow

```yaml
functions:
  wikipedia_search:
    _type: wiki_search
    max_results: 2

llms:
  nim_llm:
    _type: nim
    model_name: nvidia/nemotron-3-nano-30b-a3b
    temperature: 0.0

workflow:
  _type: react_agent
  llm_name: nim_llm
  tool_names:
    - wikipedia_search
  verbose: true
```

This creates a ReAct-style agent:

```
User Question
      |
      v
 React Agent
      |
      v
  NIM LLM
      |
      +---- wikipedia_search tool
      |
      v
 Final Response
```

The LLM decides when to call available tools based on their descriptions and the user request.

---

# Running the Agent

## Using Direct Input

```bash
dotenv run -- nat run \
  --config_file workflow.yml \
  --input "List three major achievements of NVIDIA."
```

---

## Using an Input File

```bash
dotenv run -- nat run \
  --config_file workflow.yml \
  --input_file input.txt
```

---

# Development Notes

## Adding New Tools

Before adding a new tool, inspect available NAT components:

```bash
nat info components
```

Search the exported component list:

```bash
grep -i "keyword" components.txt
```

Then add the component to `workflow.yml` using the correct `_type`.

