# loop.py – 100% NetworkX Graph-First (No agentSession)

import networkx as nx
import asyncio
from memory.context import ExecutionContextManager
from agents.base_agent import AgentRunner
from core.utils import log_step, log_error
from core.model_manager import ModelManager
from ui.visualizer import ExecutionVisualizer
from rich.live import Live
from rich.console import Console
from datetime import datetime

class AgentLoop4:
    """
    Main execution loop for the agent system using a NetworkX graph-based approach.
    Orchestrates the planning and execution of tasks.
    """

    BOOTSTRAP_NODE_ID = "ROOT"

    def __init__(self, multi_mcp, strategy="conservative"):
        """
        Initializes the AgentLoop4.

        Args:
            multi_mcp: The MultiMCP instance for tool execution.
            strategy (str, optional): The planning strategy to use. Defaults to "conservative".
        """
        self.multi_mcp = multi_mcp
        self.strategy = strategy
        self.agent_runner = AgentRunner(multi_mcp)

    def _nx_to_plan_graph_dict(self, g: nx.DiGraph) -> dict:
        """Convert a NetworkX graph into the dict format expected by ExecutionVisualizer."""
        return {
            "nodes": [{"id": node_id, **node_data} for node_id, node_data in g.nodes(data=True)],
            "links": [{"source": s, "target": t} for s, t in g.edges()],
        }

    def _build_bootstrap_graph(self, query, file_manifest, globals_schema) -> nx.DiGraph:
        """
        Create a minimal, valid graph instantly so UI can render Phase 1 immediately.
        Single node represents the Query/Planning bootstrap step.
        """
        g = nx.DiGraph()
        created_at = datetime.utcnow().isoformat()

        # Graph metadata (best-effort; ExecutionContextManager will also set these later)
        g.graph["session_id"] = None
        g.graph["original_query"] = query
        g.graph["created_at"] = created_at
        g.graph["file_manifest"] = file_manifest
        g.graph["globals_schema"] = globals_schema.copy() if isinstance(globals_schema, dict) else {}

        g.add_node(
            self.BOOTSTRAP_NODE_ID,
            # Treat this as the "Query node" that immediately shows "Planning..."
            node_type="query",
            agent="PlannerAgent",
            description="Phase 1: Planning...",
            agent_prompt="Create an execution plan (bootstrap node).",
            reads=[],
            writes=[],
            status="running",
        )
        return g

    def _inject_bootstrap_node_into_plan(self, plan_graph: nx.DiGraph):
        """
        Add the bootstrap planning node into the final plan graph as a completed root node,
        and connect it to all existing root nodes (in_degree == 0).
        """
        if not isinstance(plan_graph, nx.DiGraph):
            return
        if self.BOOTSTRAP_NODE_ID in plan_graph.nodes:
            return

        plan_graph.add_node(
            self.BOOTSTRAP_NODE_ID,
            node_type="query",
            agent="PlannerAgent",
            description="Phase 1: Planning...",
            agent_prompt="Create an execution plan (bootstrap node).",
            reads=[],
            writes=[],
            status="done",  # important: do NOT execute this node
        )

        # Connect bootstrap -> all roots (excluding itself)
        roots = [n for n in plan_graph.nodes if n != self.BOOTSTRAP_NODE_ID and plan_graph.in_degree(n) == 0]
        for n in roots:
            plan_graph.add_edge(self.BOOTSTRAP_NODE_ID, n)

    async def run(self, query, file_manifest, globals_schema, uploaded_files):
        """
        Runs the full agent workflow: File profiling, Planning, and Graph Execution.

        Args:
            query (str): The user's input query.
            file_manifest (list): Metadata about available files.
            globals_schema (dict): Schema for global variables.
            uploaded_files (list): List of files uploaded by the user.

        Returns:
            ExecutionContextManager: The context manager containing the final state and outputs.

        Raises:
            RuntimeError: If planning or graph creation fails.
        """
        # Phase 0: BOOTSTRAP GRAPH (pre-planning) so UI is never blank
        # This is the UX fix: instantly render a 1-node graph that says "Phase 1: Planning..."
        console = Console()
        bootstrap_visualizer = None
        try:
            bootstrap_graph = self._build_bootstrap_graph(query, file_manifest, globals_schema)
            bootstrap_visualizer = ExecutionVisualizer(self._nx_to_plan_graph_dict(bootstrap_graph))
        except Exception as e:
            # Never let bootstrap UI failures break the actual run
            log_error(f"Bootstrap graph/visualizer failed: {e}")

        async def _profile_and_plan():
            # Phase 1: File Profiling (if files exist)
            file_profiles = {}
            if uploaded_files:
                file_result = await self.agent_runner.run_agent(
                    "DistillerAgent",
                    {
                        "task": "profile_files",
                        "files": uploaded_files,
                        "instruction": "Profile and summarize each file's structure, columns, content type",
                        "writes": ["file_profiles"]
                    }
                )
                if file_result["success"]:
                    file_profiles = file_result["output"]

            # Phase 2: Planning with AgentRunner
            plan_result = await self.agent_runner.run_agent(
                "PlannerAgent",
                {
                    "original_query": query,
                    "planning_strategy": self.strategy,
                    "globals_schema": globals_schema,
                    "file_manifest": file_manifest,
                    "file_profiles": file_profiles
                }
            )
            return file_profiles, plan_result

        # ✅ Keep UI responsive DURING the long planning call
        if bootstrap_visualizer is not None:
            with Live(
                bootstrap_visualizer.get_layout(),
                console=console,
                refresh_per_second=6,
                transient=True,
                screen=False,
            ) as live:
                try:
                    file_profiles, plan_result = await _profile_and_plan()
                    if not plan_result.get("success"):
                        # Show failure immediately in the bootstrap UI
                        bootstrap_visualizer.mark_failed(self.BOOTSTRAP_NODE_ID, plan_result.get("error", "Planning failed"))
                        live.update(bootstrap_visualizer.get_layout())
                        raise RuntimeError(f"Planning failed: {plan_result.get('error')}")

                    # Planning succeeded -> mark bootstrap node done so user sees completion
                    bootstrap_visualizer.mark_completed(self.BOOTSTRAP_NODE_ID)
                    live.update(bootstrap_visualizer.get_layout())
                except Exception as e:
                    # Best-effort: reflect error in UI before bubbling up
                    try:
                        bootstrap_visualizer.mark_failed(self.BOOTSTRAP_NODE_ID, e)
                        live.update(bootstrap_visualizer.get_layout())
                    except Exception:
                        pass
                    raise
        else:
            # Fallback if bootstrap UI couldn't be constructed
            file_profiles, plan_result = await _profile_and_plan()

        # If we got here, plan_result should exist (either via Live path or fallback path)
        if not plan_result["success"]:
            raise RuntimeError(f"Planning failed: {plan_result['error']}")

        # Check if plan_graph exists
        if 'plan_graph' not in plan_result['output']:
            raise RuntimeError(f"PlannerAgent output missing 'plan_graph' key. Got: {list(plan_result['output'].keys())}")

        plan_graph = plan_result["output"]["plan_graph"]

        try:
            # Inject bootstrap node for continuity in the final displayed DAG (optional but nice)
            self._inject_bootstrap_node_into_plan(plan_graph)

            # Phase 3: 100% NetworkX Graph-First Execution
            context = ExecutionContextManager(
                plan_graph,
                session_id=None,
                original_query=query,
                file_manifest=file_manifest
            )

            # Add multi_mcp reference
            context.multi_mcp = self.multi_mcp

            # Initialize graph with file profiles and globals
            context.set_file_profiles(file_profiles)
            # Safer update (planner graphs may omit or mis-type globals_schema)
            gs = context.plan_graph.graph.get("globals_schema")
            if not isinstance(gs, dict):
                context.plan_graph.graph["globals_schema"] = {}
            context.plan_graph.graph["globals_schema"].update(globals_schema if isinstance(globals_schema, dict) else {})

            # Phase 4: Execute DAG with visualization
            await self._execute_dag(context)

            # Phase 5: Return the CONTEXT OBJECT, not summary
            return context

        except Exception as e:
            print(f"❌ ERROR creating ExecutionContextManager: {e}")
            import traceback
            traceback.print_exc()
            raise

    async def _execute_dag(self, context):
        """
        Executes the Directed Acyclic Graph (DAG) of tasks.
        Manages task dependencies, visualization, and parallel execution.

        Args:
            context (ExecutionContextManager): The execution context managing the graph state.
        """

        # Get plan_graph structure for visualization
        plan_graph = {
            "nodes": [
                {"id": node_id, **node_data}
                for node_id, node_data in context.plan_graph.nodes(data=True)
            ],
            "links": [
                {"source": source, "target": target}
                for source, target in context.plan_graph.edges()
            ]
        }

        # Create visualizer
        visualizer = ExecutionVisualizer(plan_graph)
        console = Console()

        # 🔧 DEBUGGING MODE: No Live display, just regular prints
        max_iterations = 20
        iteration = 0

        while not context.all_done() and iteration < max_iterations:
            iteration += 1

            # Show current state
            console.print(visualizer.get_layout())

            # Get ready nodes
            ready_steps = context.get_ready_steps()

            if not ready_steps:
                # Check for failures
                has_failures = any(
                    context.plan_graph.nodes[n]['status'] == 'failed'
                    for n in context.plan_graph.nodes
                )
                if has_failures:
                    break
                await asyncio.sleep(0.3)
                continue

            # Mark running
            for step_id in ready_steps:
                visualizer.mark_running(step_id)
                context.mark_running(step_id)

            # ✅ EXECUTE AGENTS FOR REAL
            tasks = []
            for step_id in ready_steps:
                # Log step start with description
                step_data = context.get_step_data(step_id)
                desc = step_data.get("agent_prompt", step_data.get("description", "No description"))[:60]
                log_step(f"🔄 Starting {step_id} ({step_data['agent']}): {desc}...", symbol="🚀")

                visualizer.mark_running(step_id)
                context.mark_running(step_id)
                tasks.append(self._execute_step(step_id, context))

            results = await asyncio.gather(*tasks, return_exceptions=True)

            # Process results
            for step_id, result in zip(ready_steps, results):
                step_data = context.get_step_data(step_id)
                if isinstance(result, Exception):
                    visualizer.mark_failed(step_id, result)
                    context.mark_failed(step_id, str(result))
                    log_error(f"❌ Failed {step_id}: {str(result)}")
                elif result["success"]:
                    visualizer.mark_completed(step_id)
                    await context.mark_done(step_id, result["output"])
                    log_step(f"✅ Completed {step_id} ({step_data['agent']})", symbol="✅")
                else:
                    visualizer.mark_failed(step_id, result["error"])
                    context.mark_failed(step_id, result["error"])
                    log_error(f"❌ Failed {step_id}: {result['error']}")

        # Final state
        console.print(visualizer.get_layout())

        if context.all_done():
            console.print("🎉 All tasks completed!")

    async def _execute_step(self, step_id, context):
        """
        Executes a single step (node) in the graph using the appropriate agent.
        Handles ReAct loops (tool calls) and self-correction.

        Args:
            step_id (str): The ID of the step to execute.
            context (ExecutionContextManager): The execution context.

        Returns:
            dict: The result of the step execution (success status and output).
        """
        step_data = context.get_step_data(step_id)
        agent_type = step_data["agent"]

        # Get inputs from NetworkX graph
        inputs = context.get_inputs(step_data.get("reads", []))

        def _safe_globals_schema():
            """
            Best-effort fetch of globals schema. Keep this tolerant because
            some plan_graphs may omit the key or set it non-dict.
            """
            gs = context.plan_graph.graph.get("globals_schema") or {}
            return gs.copy() if isinstance(gs, dict) else {}

        def _safe_globals_values(schema_dict):
            """
            Best-effort snapshot of ALL known global values based on schema keys.
            This fixes the 'Blind Formatter' issue where values exist in the graph
            but are not included in FormatterAgent reads/inputs.
            """
            if not schema_dict:
                return {}
            try:
                # Pull values for every declared global key
                return context.get_inputs(list(schema_dict.keys()))
            except Exception:
                return {}

        # 🔧 HELPER FUNCTION: Build agent input (consistent for both iterations)
        def build_agent_input(instruction=None, previous_output=None, iteration_context=None):
            if agent_type == "FormatterAgent":
                all_globals_schema = _safe_globals_schema()
                all_globals = _safe_globals_values(all_globals_schema)
                # Ensure Formatter sees everything, even if Planner forgot to put it in `reads`
                formatter_inputs = {**all_globals, **inputs}
                return {
                    "step_id": step_id,
                    "agent_prompt": instruction or step_data.get("agent_prompt", step_data["description"]),
                    "reads": step_data.get("reads", []),
                    "writes": step_data.get("writes", []),
                    "inputs": formatter_inputs,
                    # ✅ Critical fix: inject under the expected key name
                    "globals_schema": all_globals_schema,
                    # Optional but commonly useful: explicit globals payload
                    "globals": all_globals,

                    # Backward-compatible aliases (keep if other parts rely on these)
                    "all_globals_schema": all_globals_schema,  # ✅ explicitly injected schema
                    "all_globals": all_globals,               # ✅ explicitly injected values
                    "original_query": context.plan_graph.graph['original_query'],
                    "session_context": {
                        "session_id": context.plan_graph.graph['session_id'],
                        "created_at": context.plan_graph.graph['created_at'],
                        "file_manifest": context.plan_graph.graph['file_manifest']
                    },
                    **({"previous_output": previous_output} if previous_output else {}),
                    **({"iteration_context": iteration_context} if iteration_context else {})
                }
            else:
                return {
                    "step_id": step_id,
                    "agent_prompt": instruction or step_data.get("agent_prompt", step_data["description"]),
                    "reads": step_data.get("reads", []),
                    "writes": step_data.get("writes", []),
                    "inputs": inputs,
                    **({"previous_output": previous_output} if previous_output else {}),
                    **({"iteration_context": iteration_context} if iteration_context else {})
                }

        # Execute with ReAct Loop (Max 15 turns)
        max_turns = 15
        current_input = build_agent_input()
        iterations_data = []
        last_tool_result_str = None  # carry forward last tool result in case we must stop browsing

        def _inject_final_turn_warning(agent_input: dict, turn: int, max_turns: int) -> dict:
            """
            Injects the 'Infinite Loop' warning on the penultimate turn so the agent
            stops browsing and summarizes BEFORE hitting the hard max turn limit.
            """
            if not isinstance(agent_input, dict):
                return agent_input
            prompt = agent_input.get("agent_prompt")
            if not isinstance(prompt, str):
                return agent_input

            # ✅ Requested fix: inject "STOP BROWSING" prompt at turn == 14 (max_turns - 1)
            if turn == (max_turns - 1):
                agent_input = dict(agent_input)  # shallow copy
                agent_input["agent_prompt"] = (
                    prompt
                    + "\n\n🛑 STOP BROWSING.\n"
                      "⚠️ FINAL TURN WARNING (turn 14): You MUST stop searching/browsing now.\n"
                      "Summarize using what you already have and produce the final 'output' on this turn.\n"
                      "Do NOT call any more tools."
                )
            # Extra safety: final turn (turn 15) should also be strongly discouraged from tool use
            elif turn == max_turns:
                agent_input = dict(agent_input)
                agent_input["agent_prompt"] = (
                    prompt
                    + "\n\n🛑 STOP BROWSING.\n"
                      "🚨 FINAL TURN (turn 15): No more tools. Produce the final 'output' now."
                )
            return agent_input

        def _latest_non_tool_output(iters: list) -> dict:
            """
            Best-effort fallback to avoid returning a bare 'call_tool' request
            as the final output (common cause of 'No output produced').
            """
            for item in reversed(iters or []):
                out = (item or {}).get("output")
                if isinstance(out, dict) and not out.get("call_tool") and not out.get("call_self"):
                    return out
            # If everything is tool/self calls, just return the last output we saw.
            if iters:
                out = iters[-1].get("output")
                return out if isinstance(out, dict) else {"error": "No output produced"}
            return {"error": "No output produced"}

        for turn in range(1, max_turns + 1):
            log_step(f"🔄 {agent_type} Iteration {turn}/{max_turns}", symbol="🔄")

            # Run Agent
            # ✅ Inject warning *before* the penultimate turn runs
            turn_input = _inject_final_turn_warning(current_input, turn, max_turns)
            result = await self.agent_runner.run_agent(agent_type, turn_input)

            if not result["success"]:
                return result

            output = result["output"]
            iterations_data.append({"iteration": turn, "output": output})

            # Update step data with iterations so far
            step_data = context.get_step_data(step_id)
            step_data['iterations'] = iterations_data

            # 1. Check for 'call_tool' (ReAct)
            if output.get("call_tool"):
                tool_call = output["call_tool"]
                tool_name = tool_call.get("name")
                tool_args = tool_call.get("arguments", {})

                # 🛑 Hard guard: block tool calls on turn 14+ so we don't burn tokens "browsing forever"
                if turn >= (max_turns - 1):
                    log_error(
                        f"🛑 STOP BROWSING: blocked tool call '{tool_name}' on turn {turn}/{max_turns} "
                        f"for step {step_id}."
                    )
                    # If we still have a turn left (turn 15), force a summary without running tools.
                    # If this is already the last turn, salvage the best non-tool output we have.
                    if turn == max_turns:
                        return {"success": True, "output": _latest_non_tool_output(iterations_data)}

                    instruction = (
                        "🛑 STOP BROWSING. Tool/browse calls are blocked now.\n"
                        "Use only the information you already have (including any prior tool results) and "
                        "produce the final 'output' on the next turn. Do NOT call tools."
                    )
                    current_input = build_agent_input(
                        instruction=instruction,
                        previous_output=output,
                        iteration_context={
                            "tool_result": last_tool_result_str or "",
                            "blocked_tool_call": {"name": tool_name, "arguments": tool_args},
                        },
                    )
                    continue

                log_step(f"🛠️ Executing Tool: {tool_name}", payload=tool_args, symbol="⚙️")

                try:
                    # Execute tool via MultiMCP
                    tool_result = await self.multi_mcp.route_tool_call(tool_name, tool_args)

                    # Serialize result content
                    if isinstance(tool_result.content, list):
                        result_str = "\n".join([str(item.text) for item in tool_result.content if hasattr(item, "text")])
                    else:
                        result_str = str(tool_result.content)
                    last_tool_result_str = result_str

                    # Log result (truncated)
                    log_step(f"✅ Tool Result", payload={"result_preview": result_str[:200] + "..."}, symbol="🔌")

                    # Prepare input for next iteration
                    instruction = (
                        output.get("next_instruction")
                        or output.get("thought")
                        or "Use the tool result to generate the final output."
                    )
                    # Keep/strengthen the warning when we are about to hit the limit.
                    if turn == (max_turns - 1):
                        instruction += (
                            "\n\n🛑 STOP BROWSING. FINAL TURN WARNING: "
                            "You MUST provide the final 'output' now. Do not call any more tools."
                        )

                    current_input = build_agent_input(
                        instruction=instruction,
                        previous_output=output,
                        iteration_context={"tool_result": result_str}
                    )
                    continue # Loop to next turn

                except Exception as e:
                    log_error(f"Tool Execution Failed: {e}")
                    # Feed error back to agent
                    current_input = build_agent_input(
                        instruction="The tool execution failed. Try a different approach or tool.",
                        previous_output=output,
                        iteration_context={"tool_result": f"Error: {str(e)}"}
                    )
                    continue

            # 2. Check for call_self (Legacy/Advanced recursion)
            elif output.get("call_self"):
                # Handle code execution if needed
                if context._has_executable_code(output):
                    execution_result = await context._auto_execute_code(step_id, output)
                    if execution_result.get("status") == "success":
                        execution_data = execution_result.get("result", {})
                        inputs = {**inputs, **execution_data}  # Update inputs for iteration 2

                        # Persist intermediate results so the sandbox can see them on the next run.
                        # Without this, variables like `found_urls_T002` produced in iteration 1
                        # are not injected into the execution environment for iteration 2, causing
                        # NameError when the next code_variant tries to use them.
                        globals_schema = context.plan_graph.graph.get("globals_schema", {})
                        if isinstance(globals_schema, dict) and isinstance(execution_data, dict):
                            for k, v in execution_data.items():
                                try:
                                    globals_schema[k] = context._ensure_parsed_value(v)
                                except Exception:
                                    globals_schema[k] = v
                            context.plan_graph.graph["globals_schema"] = globals_schema

                # Prepare input for next iteration
                current_input = build_agent_input(
                    instruction=output.get("next_instruction", "Continue the task"),
                    previous_output=output,
                    iteration_context=output.get("iteration_context", {})
                )
                continue

            # 3. Success (No tool call, just output)
            else:
                return result

        # If loop finishes without returning (max turns reached): Return PARTIAL SUCCESS to allow graph continuation
        log_error(f"Max iterations ({max_turns}) reached for {step_id}. Returning last output (incomplete).")
        # ✅ Prefer the latest non-tool/non-self output to avoid "No output produced"
        return {"success": True, "output": _latest_non_tool_output(iterations_data)}

    async def _handle_failures(self, context):
        """Handle failures via mid-session replanning"""
        # TODO: Implement mid-session replanning with PlannerAgent
        log_error("Mid-session replanning not yet implemented")
