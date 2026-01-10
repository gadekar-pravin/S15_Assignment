
# 🚀 S16 NetworkX: The Modern Agent Architecture

Welcome to the **S16 NetworkX Agent System**, a robust, graph-first agent orchestration framework.
This system replaces manual graph management with a dynamic Directed Acyclic Graph (DAG) structure managed by `networkx`, integrating modern tools for planning, execution, and persistent memory.

## 🏗️ Architecture

### 1. The Core (Graph Engine)
*   **File**: `core/loop.py`
*   **Logic**: Uses `networkx.DiGraph` to manage the execution plan.
*   **Context**: Strictly isolated execution context. Node B only sees Node A's output if an explicit dependency `A -> B` exists.
*   **Execution**: Steps are executed in parallel where possible, respecting dependencies.
*   **Summarizer**: A special agent with **Global Read Access** responsible for synthesizing the final output.

### 2. The Tools (Hybrid Stack)
*   **Browser**: **Hybrid Mode** via `mcp_servers/server_browser.py`.
    *   **Fast Search**: `duckduckgo`, `bing`, etc. (Text-based, robust fallbacks).
    *   **Deep Action**: `browser-use` (Vision-based) for complex interactions.
*   **Memory**: **Dual Layer**.
    *   **Short-term**: Session Context (NetworkX attributes) for the current run.
    *   **Long-term**: `mem0` (User Profile, Local Vector Store) for persistent knowledge.
*   **Sandbox**: Secure Python code execution environment (`tools/sandbox.py`), wrapped as an MCP tool.
*   **RAG**: Local Retrieval Augmented Generation via `mcp_servers/server_rag.py` using FAISS and local embeddings.

### 3. Folder Structure
```text
16_NetworkX/
├── agents/             # AgentRunners (Logic & Configuration)
├── config/             # YAML Configs + Models
├── core/               # Main Loop, Context Manager & Utilities
├── memory/             # Context Management & Mem0 Storage
├── mcp_servers/        # Model Context Protocol Servers (Browser, RAG, Sandbox)
├── prompts/            # System Prompts (Markdown)
├── tools/              # Helper Scripts (Sandbox, etc.)
├── ui/                 # Visualization Tools (Rich CLI & Gradio)
└── app.py              # Main Entry Point
```

## 🏃‍♂️ How to Run

### Prerequisites
*   Python 3.10+
*   Install dependencies: `uv sync` or `pip install -r requirements.txt` (ensure `networkx`, `rich`, `fastmcp`, `mem0`, `playwright`, etc. are installed).
*   Set up environment variables in `.env` (e.g., `GEMINI_API_KEY`, `OPENAI_API_KEY`).

### Interactive CLI Mode
Run the main application in the terminal:
```bash
uv run app.py
```
Type your query (e.g., "Plan a 3 day trip to Tokyo") and watch the execution graph in real-time.

### Web UI Mode
Launch the Gradio-based web interface:
```bash
uv run app.py --ui
```
Access the UI at `http://localhost:7860`.

### Automated Tests
Run the comprehensive flow test:
```bash
uv run test_flow_comprehensive.py
```

## 🛠️ Configuration
*   **Agents**: `config/agent_config.yaml` maps Agents -> Prompts -> Tools.
*   **Models**: `config/models.json` defines LLMs (Gemini, Ollama, OpenAI).
*   **Prompts**: Edit `prompts/*.md` to change agent behaviors.

## 🔮 Roadmap
1.  **UI**: Enhance `ui/visualizer.py` with more interactive graph features.
2.  **E2B**: Fully replace the local `tools/sandbox.py` with the E2B SDK for cloud-based sandboxing.
3.  **Mem0**: Enable active learning in `SummarizerAgent` to automatically update long-term memory.
