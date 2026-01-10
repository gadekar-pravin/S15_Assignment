from rich import print
from datetime import datetime
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

def log_step(title: str, payload=None, symbol: str = "🟢"):
    """
    Logs a step in the execution process with a title and optional payload.

    Args:
        title (str): The title of the step.
        payload (Any, optional): Data to display (will be pretty-printed). Defaults to None.
        symbol (str, optional): An emoji symbol to prefix the title. Defaults to "🟢".
    """
    print(f"\n[b]{symbol} {title}[/b]")
    if payload:
        from pprint import pprint
        pprint(payload)

def log_error(message: str, err: Exception = None):
    """
    Logs an error message and optional exception details.

    Args:
        message (str): The error message.
        err (Exception, optional): The exception object, if any. Defaults to None.
    """
    print(f"\n[red]❌ {message}[/red]")
    if err:
        print(f"[dim]{str(err)}[/dim]")

def log_json_block(title: str, block):
    """
    Logs a JSON-like object (dict or list) in a styled panel.

    Args:
        title (str): The title of the panel.
        block (dict | list | Any): The data object to display.
    """
    from rich.panel import Panel
    from rich.console import Console

    console = Console()

    def truncate(value, max_length=150):
        value = str(value)
        return value if len(value) <= max_length else value[:max_length] + "..."

    def style_key(key):
        return f"[bold cyan]{key}[/bold cyan]"

    def format_inline_dict(d: dict):
        return (
            "{ " + ", ".join(f"{style_key(k)}: {truncate(v)}" for k, v in d.items()) + " }"
        )

    def format_block(obj):
        lines = []
        if isinstance(obj, dict):
            for k, v in obj.items():
                if isinstance(v, list) and all(isinstance(i, dict) for i in v):
                    lines.append(f"{style_key(k)}:")
                    for item in v:
                        lines.append("  " + format_inline_dict(item))
                elif isinstance(v, dict):
                    lines.append(f"{style_key(k)}:")
                    for sk, sv in v.items():
                        lines.append(f"  {style_key(sk)}: {truncate(sv)}")
                else:
                    lines.append(f"{style_key(k)}: {truncate(v)}")
        else:
            lines.append(truncate(obj))
        return "\n".join(lines)

    content = format_block(block)
    panel = Panel(content, title=f"📌 {title}", title_align="left", border_style="cyan", expand=False)
    console.print(panel)


def render_graph(graph, depth=1):
    """
    Renders a visual representation of the agent execution graph (NetworkX DiGraph).

    Args:
        graph (networkx.DiGraph): The graph to render.
        depth (int, optional): The level of detail to display (1, 2, or more). Defaults to 1.
    """
    from rich.panel import Panel
    from rich.table import Table
    from rich.console import Console
    from rich.text import Text
    from rich import print

    console = Console()

    def truncate(text, limit=200):
        text = str(text)
        return text if len(text) <= limit else text[:limit] + "..."

    print("\n[bold yellow]🧠 Agent Step Graph (Depth {})[/bold yellow]".format(depth))

    table = Table(show_header=True, header_style="bold magenta", box=None)
    table.add_column("Step ID", style="cyan", no_wrap=True)
    table.add_column("Type")
    table.add_column("Status", style="bold")
    table.add_column("Description", style="dim")

    # Handle NetworkX DiGraph
    if hasattr(graph, "nodes"):
        nodes_iter = graph.nodes
    else:
        nodes_iter = []

    for node_id in nodes_iter:
        # Check if node data is dict or object
        raw_node = graph.nodes[node_id]
        if "data" in raw_node:
             # S15 Manual style object wrapper
             node = raw_node["data"]
             desc = truncate(node.description)
             status = node.status
             tipo = node.type
             result = node.result
             error = node.error
             perception = node.perception
        else:
             # Just dict attributes
             node = raw_node
             desc = truncate(node.get("description", ""))
             status = node.get("status", "pending")
             tipo = node.get("agent_type", "CODE") # Default to CODE/agent_type
             result = node.get("output", None)
             error = node.get("error", None)
             perception = None

        if depth == 1:
            table.add_row(str(node_id), str(tipo), str(status), desc)

        elif depth == 2:
            summary = desc
            if result:
                summary += " ↳ [green]Has Result[/green]"
            if error:
                summary += f" ⚠️ {truncate(error)}"
            if perception:
                p = perception
                status_txt = f"🧠 goal={p.get('original_goal_achieved', False)} | summary={truncate(p.get('solution_summary', ''))}"
                summary += f" ({status_txt})"
            table.add_row(str(node_id), str(tipo), str(status), truncate(summary))

        else:
            table.add_row(str(node_id), str(tipo), str(status), truncate(str(node)))

    console.print(Panel(table, title="Agent Step Tracker", border_style="blue"))

import json
from pathlib import Path
from datetime import datetime
from rich import print

def get_log_folder(session_id: str, base_dir: str = None) -> Path:
    """
    Creates and returns a directory path for storing logs, organized by date.

    Args:
        session_id (str): The unique identifier for the session (unused in path construction but kept for interface).
        base_dir (str, optional): The base directory for logs. Defaults to 'memory/session_logs' relative to the repo root.

    Returns:
        Path: The path to the created log folder.
    """
    if base_dir is None:
        base_dir = Path(__file__).parent.parent / "memory" / "session_logs"
    now = datetime.now()
    folder = Path(base_dir) / str(now.year) / f"{now.month:02d}" / f"{now.day:02d}"
    folder.mkdir(parents=True, exist_ok=True)
    return folder

def save_json_log(obj: dict, path: Path):
    """
    Saves a dictionary to a JSON file.

    Args:
        obj (dict): The data to save.
        path (Path): The file path where the JSON will be saved.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, indent=2)
    print(f"\n\n[green]📝 Saved JSON log:[/green] {path}\n")

def append_step_log(session_id: str, step_data: dict, base_dir: str = None):
    """
    Appends a step execution log to a session-specific JSON file.

    Args:
        session_id (str): The session identifier.
        step_data (dict): The data regarding the step to log.
        base_dir (str, optional): Base directory for logs. Defaults to None.
    """
    folder = get_log_folder(session_id, base_dir)
    step_path = folder / f"{session_id}_steps.json"
    if step_path.exists():
        with open(step_path, "r", encoding="utf-8") as f:
            logs = json.load(f)
    else:
        logs = []

    logs.append(step_data)
    with open(step_path, "w", encoding="utf-8") as f:
        json.dump(logs, f, indent=2)
    print(f"[cyan]🔄 Step log updated:[/cyan] {step_path}")

def save_final_plan(session_id: str, final_data: dict, base_dir: str = None):
    """
    Saves the final execution plan to a JSON file.

    Args:
        session_id (str): The session identifier.
        final_data (dict): The final plan data to save.
        base_dir (str, optional): Base directory for logs. Defaults to None.
    """
    folder = get_log_folder(session_id, base_dir)
    plan_path = folder / f"{session_id}.json"
    save_json_log(final_data, plan_path)
