import asyncio
import networkx as nx
from datetime import datetime
from rich.console import Console
from rich.text import Text
from rich.live import Live
from rich.tree import Tree
from rich.layout import Layout
from rich.panel import Panel
from rich.align import Align
from rich.table import Table

class ExecutionVisualizer:
    """
    Visualizes the execution of an agent workflow graph using the Rich library.
    Displays a real-time DAG tree and execution logs.
    """

    def __init__(self, plan_graph):
        """
        Initializes the ExecutionVisualizer.

        Args:
            plan_graph (dict): The execution plan graph structure (nodes and links).
        """
        self.log_messages = []

        # Build NetworkX graph exactly like your test.py
        self.G = nx.DiGraph()

        # Add all nodes with their data
        for node in plan_graph.get("nodes", []):
            node_id = node["id"]

            # 🔧 FIX: Handle ROOT node specially (no agent field)
            if node_id == "ROOT":
                self.G.add_node(
                    node_id,
                    status="completed",
                    started=None,
                    completed=None,
                    agent="System",  # ✅ Add default agent for ROOT
                    description=node.get("description", "Initial Query")
                )
            else:
                # 🔧 FIX: Handle regular nodes (must have agent field)
                if "agent" not in node:
                    print(f"⚠️  Warning: Node {node_id} missing 'agent' field, using default")
                    agent = "UnknownAgent"
                else:
                    agent = node["agent"]

                self.G.add_node(
                    node_id,
                    status=node.get("status", "pending"),
                    started=None,
                    completed=None,
                    agent=agent,
                    description=node.get("description", f"Task {node_id}")
                )

        # Add edges exactly like your test.py
        for edge in plan_graph.get("links", []):
            self.G.add_edge(edge["source"], edge["target"])

    def get_log_panel(self):
        """
        Generates the log panel displaying the last few execution messages.

        Returns:
            Panel: A Rich Panel containing the formatted log messages.
        """
        log_text = "\n".join(self.log_messages[-8:]) or "🚀 Starting execution..."
        return Panel(Align.left(log_text), title="📋 Execution Log", border_style="cyan")

    def build_tree(self, node_id="ROOT", visited_global=None):
        """
        Builds a Rich Tree representing the execution DAG, handling converging paths.

        Args:
            node_id (str, optional): The starting node ID. Defaults to "ROOT".
            visited_global (set, optional): Set of visited nodes to handle convergence. Defaults to None.

        Returns:
            Tree: The visual tree representation.
        """
        if visited_global is None:
            visited_global = set()

        def build_subtree(current_node, path_visited):
            # Prevent infinite loops in current path
            if current_node in path_visited:
                return Tree(Text(f"[CYCLE: {current_node}]", style="red"))

            path_visited = path_visited | {current_node}

            node_data = self.G.nodes[current_node]
            status = node_data["status"]
            agent = node_data["agent"]
            description = node_data["description"]

            # Status symbols
            status_symbol = {
                "pending": "🔲", "running": "🔄", "completed": "✅", "failed": "❌"
            }[status]

            # Format label
            if current_node == "ROOT":
                label = Text(f"ROOT {status_symbol} {description}")
            else:
                short_desc = description[:60] + "..." if len(description) > 60 else description
                label = Text(f"{current_node} {status_symbol} {agent} → {short_desc}")

            # Styling
            if status == "completed":
                label.stylize("green")
            elif status == "running":
                label.stylize("yellow")
            elif status == "failed":
                label.stylize("red")
            else:
                label.stylize("dim")

            tree = Tree(label)

            # Get successors
            successors = list(self.G.successors(current_node))

            if not successors:
                return tree

            # Check each successor for convergence
            for child in successors:
                parents = list(self.G.predecessors(child))

                if len(parents) > 1:
                    # This is a convergence node
                    if child not in visited_global:
                        # First time seeing this convergence node - show it with all parents
                        visited_global.add(child)

                        # Create convergence indicator
                        parent_names = [p for p in parents if p != current_node]
                        if parent_names:
                            conv_label = Text(f"[+ {', '.join(parent_names)}] → {child}")
                            conv_label.stylize("cyan bold")
                            conv_tree = Tree(conv_label)
                            conv_tree.add(build_subtree(child, path_visited))
                            tree.add(conv_tree)
                        else:
                            # This is the last parent to reach convergence
                            tree.add(build_subtree(child, path_visited))
                    else:
                        # Already shown this convergence node
                        ref_label = Text(f"→ {child} [see above]")
                        ref_label.stylize("dim italic")
                        tree.add(Tree(ref_label))
                else:
                    # Regular single-parent node
                    tree.add(build_subtree(child, path_visited))

            return tree

        return build_subtree(node_id, set())

    def get_layout(self):
        """
        Constructs the overall layout with the tree and log panel.

        Returns:
            Layout: The configured Rich Layout.
        """
        layout = Layout()
        layout.split_column(
            Layout(name="tree", ratio=3),
            Layout(name="log", size=8)
        )
        layout["tree"].update(
            Panel(self.build_tree(), title="🤖 Agent Execution DAG", border_style="white")
        )
        layout["log"].update(self.get_log_panel())
        return layout

    # Execution methods exactly like your test.py
    def get_ready_nodes(self):
        """
        Identifies nodes that are ready to execute (pending and dependencies met).

        Returns:
            list: List of ready node IDs.
        """
        ready = []
        for node in self.G.nodes:
            if self.G.nodes[node]["status"] != "pending":
                continue
            preds = list(self.G.predecessors(node))
            if all(self.G.nodes[p]["status"] == "completed" for p in preds):
                ready.append(node)
        return ready

    def mark_running(self, node_id):
        """
        Updates the status of a node to 'running' and logs the event.

        Args:
            node_id (str): The node ID.
        """
        timestamp = datetime.now().strftime("%H:%M:%S")
        agent = self.G.nodes[node_id]["agent"]
        desc = self.G.nodes[node_id]["description"][:40] + "..."
        self.log_messages.append(f"[{timestamp}] 🔄 Starting {node_id} ({agent}): {desc}")
        self.G.nodes[node_id]["status"] = "running"
        self.G.nodes[node_id]["started"] = datetime.now()

    def mark_completed(self, node_id):
        """
        Updates the status of a node to 'completed' and logs the event.

        Args:
            node_id (str): The node ID.
        """
        timestamp = datetime.now().strftime("%H:%M:%S")
        agent = self.G.nodes[node_id]["agent"]
        self.log_messages.append(f"[{timestamp}] ✅ Completed {node_id} ({agent})")
        self.G.nodes[node_id]["status"] = "completed"
        self.G.nodes[node_id]["completed"] = datetime.now()

    def mark_failed(self, node_id, error=None):
        """
        Updates the status of a node to 'failed' and logs the error.

        Args:
            node_id (str): The node ID.
            error (Any, optional): The error object or message.
        """
        timestamp = datetime.now().strftime("%H:%M:%S")
        agent = self.G.nodes[node_id]["agent"]
        error_msg = f": {str(error)[:30]}..." if error else ""
        self.log_messages.append(f"[{timestamp}] ❌ Failed {node_id} ({agent}){error_msg}")
        self.G.nodes[node_id]["status"] = "failed"

    def is_finished(self):
        """
        Checks if the entire workflow has finished (all nodes completed or failed).

        Returns:
            bool: True if finished.
        """
        return all(
            self.G.nodes[n]["status"] in ["completed", "failed"]
            for n in self.G.nodes if n != "ROOT"
        )
