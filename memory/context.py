# contextManager.py – 100% NetworkX Graph-First (SIMPLIFIED)

import ast
import networkx as nx
import json
import time
import re
from typing import Any, Optional, Tuple, Dict
from datetime import datetime
from pathlib import Path
import asyncio
from tools.sandbox import run_user_code
from rich.console import Console
from rich.prompt import Prompt
from rich.panel import Panel
from rich.text import Text

class ExecutionContextManager:
    """
    Manages the execution context for an agent workflow using a NetworkX graph.
    Handles step dependencies, state management, code execution, user interaction,
    and result storage.
    """

    def __init__(self, plan_graph: dict, session_id: str = None, original_query: str = None, file_manifest: list = None, debug_mode: bool = False):
        """
        Initializes the ExecutionContextManager.

        Args:
            plan_graph (dict): The execution plan defined as a graph structure (nodes and edges).
            session_id (str, optional): Unique session identifier. Defaults to a timestamp-based ID.
            original_query (str, optional): The user's original query.
            file_manifest (list, optional): List of available files.
            debug_mode (bool, optional): Whether to run in debug mode (suppresses auto-save). Defaults to False.
        """
        # 🎯 Build NetworkX graph with ALL data
        self.plan_graph = nx.DiGraph()

        # Store session metadata in graph attributes
        self.plan_graph.graph['session_id'] = session_id or str(int(time.time()))[-8:]
        self.plan_graph.graph['original_query'] = original_query
        self.plan_graph.graph['file_manifest'] = file_manifest or []
        self.plan_graph.graph['created_at'] = datetime.utcnow().isoformat()
        self.plan_graph.graph['status'] = 'running'
        self.plan_graph.graph['globals_schema'] = {}

        # Add ROOT node
        self.plan_graph.add_node("ROOT",
            description="Initial Query",
            agent="System",
            status='completed',
            output=None,
            error=None,
            cost=0.0,
            start_time=None,
            end_time=None,
            execution_time=0.0
        )

        # Build plan DAG
        for node in plan_graph.get("nodes", []):
            self.plan_graph.add_node(node["id"],
                **node,
                status='pending',
                output=None,
                error=None,
                cost=0.0,
                start_time=None,
                end_time=None,
                execution_time=0.0
            )

        for edge in plan_graph.get("edges", []):
            self.plan_graph.add_edge(edge["source"], edge["target"])

        self.debug_mode = debug_mode
        self._live_display = None

    def get_ready_steps(self):
        """
        Returns a list of steps that are ready to execute.
        A step is ready if it is pending and all its predecessors are completed.

        Returns:
            list: List of node IDs for ready steps.
        """
        ready = []

        for node_id in self.plan_graph.nodes:
            node_data = self.plan_graph.nodes[node_id]

            if node_id == "ROOT":
                continue

            status = node_data.get('status', 'pending')
            if status in ['completed', 'failed', 'running']:
                continue

            # Check if all dependencies are complete
            predecessors = list(self.plan_graph.predecessors(node_id))
            all_deps_complete = all(
                self.plan_graph.nodes[p].get('status', 'pending') == 'completed'
                for p in predecessors
            )

            if all_deps_complete:
                ready.append(node_id)

        return ready

    def mark_running(self, step_id):
        """
        Marks a step as running and records the start time.

        Args:
            step_id (str): The ID of the step to mark.
        """
        self.plan_graph.nodes[step_id]['status'] = 'running'
        self.plan_graph.nodes[step_id]['start_time'] = datetime.utcnow().isoformat()
        self._auto_save()

    def _has_executable_code(self, output):
        """
        Detects if the agent's output contains executable code patterns.

        Args:
            output (dict): The agent's output.

        Returns:
            bool: True if code execution patterns are found, False otherwise.
        """
        if not isinstance(output, dict):
            return False

        return (
            "code_variants" in output or
            any(k.startswith("CODE_") for k in output.keys()) or
            any(key in output for key in ["tool_calls", "schedule_tool", "browser_commands", "python_code"])
        )

    def _ensure_parsed_value(self, value, *, _depth=0, max_depth=30, max_str_len=50_000):
        """
        Recursively coerce stringified literals into Python objects.
        Safe-by-default: uses ast.literal_eval with guardrails.
        """
        if _depth > max_depth:
            return value

        # Strings: attempt parse only when it really looks like a literal
        if isinstance(value, str):
            s = value.strip()
            if not s:
                return value
            if len(s) > max_str_len:
                return value

            low = s.lower()
            if low == "true":
                return True
            if low == "false":
                return False
            if low in ("none", "null"):
                return None

            starts_ends_like_container = (
                (s[0] == "[" and s[-1] == "]") or
                (s[0] == "{" and s[-1] == "}") or
                (s[0] == "(" and s[-1] == ")")
            )
            starts_ends_like_quoted = (s[0] in ("'", '"') and s[-1] == s[0])
            looks_like_number = s[0].isdigit() or s[0] in "+-."
            looks_like_literal = (
                starts_ends_like_container or
                starts_ends_like_quoted or
                looks_like_number
            )

            if not looks_like_literal:
                return value

            try:
                parsed = ast.literal_eval(s)
            except (ValueError, SyntaxError, TypeError, MemoryError, RecursionError):
                return value

            return self._ensure_parsed_value(parsed, _depth=_depth + 1, max_depth=max_depth, max_str_len=max_str_len)

        if isinstance(value, list):
            return [self._ensure_parsed_value(v, _depth=_depth + 1, max_depth=max_depth, max_str_len=max_str_len) for v in value]

        if isinstance(value, tuple):
            return tuple(self._ensure_parsed_value(v, _depth=_depth + 1, max_depth=max_depth, max_str_len=max_str_len) for v in value)

        if isinstance(value, dict):
            return {k: self._ensure_parsed_value(v, _depth=_depth + 1, max_depth=max_depth, max_str_len=max_str_len) for k, v in value.items()}

        if isinstance(value, set):
            return {self._ensure_parsed_value(v, _depth=_depth + 1, max_depth=max_depth, max_str_len=max_str_len) for v in value}

        if isinstance(value, frozenset):
            return frozenset(self._ensure_parsed_value(v, _depth=_depth + 1, max_depth=max_depth, max_str_len=max_str_len) for v in value)

        return value

    # ---------------------------
    # Robust extraction fallbacks
    # ---------------------------
    _META_KEYS = {
        # common meta keys we should ignore when attempting singleton mapping
        "cost", "input_tokens", "output_tokens",
        "execution_result", "execution_status", "execution_error", "execution_time", "executed_variant",
        "code_variants", "tool_calls", "schedule_tool", "browser_commands", "python_code",
        "call_self", "agent", "status", "error",
    }

    def _short_repr(self, v: Any, max_len: int = 240) -> str:
        try:
            s = repr(v)
        except Exception:
            s = f"<unreprable {type(v).__name__}>"
        if len(s) > max_len:
            return s[: max_len - 3] + "..."
        return s

    def _normalize_key(self, k: Any) -> str:
        if not isinstance(k, str):
            k = str(k)
        # normalize to compare keys even if agent changes casing/underscores/spaces
        return re.sub(r"[^a-z0-9]+", "", k.strip().lower())

    def _walk_find_key(self, obj: Any, target_norm: str, *, _depth: int = 0, max_depth: int = 6) -> Tuple[bool, Any]:
        """
        Recursively search dict/list-like structures for a key that matches target_norm
        (normalized). Returns (found, value).
        """
        if _depth > max_depth:
            return False, None

        if isinstance(obj, dict):
            # direct normalized match at this level
            for k, v in obj.items():
                if self._normalize_key(k) == target_norm:
                    return True, v
            # recurse
            for v in obj.values():
                found, val = self._walk_find_key(v, target_norm, _depth=_depth + 1, max_depth=max_depth)
                if found:
                    return True, val
            return False, None

        if isinstance(obj, (list, tuple)):
            for item in obj:
                found, val = self._walk_find_key(item, target_norm, _depth=_depth + 1, max_depth=max_depth)
                if found:
                    return True, val
            return False, None

        return False, None

    def _walk_find_key_suffix(self, obj: Any, suffix_norm: str, *, _depth: int = 0, max_depth: int = 6) -> Tuple[bool, Any, str]:
        """
        Recursively search for any key whose normalized form ends with the given suffix_norm.
        Used as a forgiving fallback when the agent returns the right step-id suffix
        (e.g., `_T004`) but drops or alters the prefix (common with FormatterAgent).
        """
        if _depth > max_depth:
            return False, None, ""

        if isinstance(obj, dict):
            for k, v in obj.items():
                if self._normalize_key(k).endswith(suffix_norm):
                    return True, v, k
            for v in obj.values():
                found, val, src = self._walk_find_key_suffix(v, suffix_norm, _depth=_depth + 1, max_depth=max_depth)
                if found:
                    return True, val, src
            return False, None, ""

        if isinstance(obj, (list, tuple)):
            for item in obj:
                found, val, src = self._walk_find_key_suffix(item, suffix_norm, _depth=_depth + 1, max_depth=max_depth)
                if found:
                    return True, val, src
            return False, None, ""

        return False, None, ""

    def _parse_jsonish_text(self, text: str, *, max_len: int = 80_000) -> Optional[Any]:
        """
        Try to parse JSON (or python-literal-ish) content embedded in text.
        - fenced ```json ... ```
        - first {...} block
        - direct json.loads
        - ast.literal_eval as a final attempt (guarded)
        """
        if not isinstance(text, str):
            return None
        s = text.strip()
        if not s or len(s) > max_len:
            return None

        # 1) fenced code block (```json ... ``` or ``` ... ```)
        fence = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", s, flags=re.IGNORECASE)
        if fence:
            candidate = fence.group(1).strip()
            parsed = self._parse_jsonish_text(candidate, max_len=max_len)
            if parsed is not None:
                return parsed

        # 2) direct json
        if s[:1] in "{[":
            try:
                return json.loads(s)
            except Exception:
                pass

        # 3) find a JSON-looking object inside text: from first '{' to last '}'
        if "{" in s and "}" in s:
            start = s.find("{")
            end = s.rfind("}")
            if 0 <= start < end:
                blob = s[start:end + 1].strip()
                try:
                    return json.loads(blob)
                except Exception:
                    # sometimes it's python-dict formatted
                    try:
                        return self._ensure_parsed_value(blob)
                    except Exception:
                        pass

        # 4) python literal as last resort (guarded by _ensure_parsed_value heuristics)
        try:
            parsed = self._ensure_parsed_value(s)
            if parsed is not s:
                return parsed
        except Exception:
            pass

        return None

    def _extract_from_mapping(
        self,
        mapping: Any,
        write_key: str,
        *,
        allow_singleton: bool,
        writes_count: int
    ) -> Tuple[bool, Any, str]:
        """
        Try to extract write_key from mapping-like objects (dict or parsed structures).
        Returns (found, value, source_label).
        """
        target_norm = self._normalize_key(write_key)

        # If it's a string, try parsing it into something structured
        if isinstance(mapping, str):
            parsed = self._parse_jsonish_text(mapping)
            if parsed is None:
                return False, None, ""
            return self._extract_from_mapping(parsed, write_key, allow_singleton=allow_singleton, writes_count=writes_count)

        # Dict: exact key, normalized key, deep search, singleton
        if isinstance(mapping, dict):
            if write_key in mapping:
                return True, mapping[write_key], "mapping:exact_key"

            # normalized key match at top level
            for k, v in mapping.items():
                if self._normalize_key(k) == target_norm:
                    return True, v, f"mapping:normalized_key({k})"

            # deep search
            found, val = self._walk_find_key(mapping, target_norm)
            if found:
                return True, val, "mapping:deep_search"

            # singleton mapping only if it’s safe to do so
            if allow_singleton and writes_count == 1:
                # ignore meta-ish keys when considering singleton
                payload_items = [(k, v) for k, v in mapping.items() if str(k) not in self._META_KEYS]
                if len(payload_items) == 1:
                    k, v = payload_items[0]
                    return True, v, f"mapping:singleton({k})"

            return False, None, ""

        # List/tuple: deep search inside elements (useful if agent returns a list of dicts)
        if isinstance(mapping, (list, tuple)):
            found, val = self._walk_find_key(mapping, target_norm)
            if found:
                return True, val, "mapping:list_deep_search"
            # If single write and the structure is "the answer itself"
            if allow_singleton and writes_count == 1 and len(mapping) == 1:
                return True, mapping[0], "mapping:list_singleton"
            return False, None, ""

        # Scalar: only accept as singleton value if single write key
        if allow_singleton and writes_count == 1:
            return True, mapping, "mapping:scalar_singleton"

        return False, None, ""

    def _get_final_answer_field(self, output: Dict[str, Any]) -> Optional[Any]:
        """
        Pull final answer-like fields from common variants.
        """
        if not isinstance(output, dict):
            return None
        for k in ("final_answer", "finalAnswer", "final", "answer"):
            if k in output:
                return output.get(k)
        # sometimes nested under output
        inner = output.get("output")
        if isinstance(inner, dict):
            for k in ("final_answer", "finalAnswer", "final", "answer"):
                if k in inner:
                    return inner.get(k)
        return None

    def _extract_write_value(self, write_key: str, *, writes: list, output: Any, execution_result: Any) -> Tuple[bool, Any, str]:
        """
        3-strategy extraction:
          1) code execution produced variable
          2) present in agent JSON output
          3) present/hidden in final_answer (parse if needed)
        Returns (found, value, source).
        """
        writes_count = len(writes) if isinstance(writes, list) else 1

        # Strategy 1: execution_result (best)
        if isinstance(execution_result, dict) and execution_result.get("status") == "success":
            # Try multiple common shapes
            candidate_fields = []
            for k in ("result", "locals", "globals", "variables", "data", "output"):
                if k in execution_result and execution_result[k] is not None:
                    candidate_fields.append((k, execution_result[k]))

            for field_name, candidate in candidate_fields:
                found, val, src = self._extract_from_mapping(
                    candidate, write_key,
                    allow_singleton=True,
                    writes_count=writes_count
                )
                if found:
                    return True, val, f"exec:{field_name}/{src}"

        # Strategy 2: agent JSON output (root + nested + deep + singleton)
        if isinstance(output, dict):
            # Root first
            found, val, src = self._extract_from_mapping(
                output, write_key,
                allow_singleton=True,
                writes_count=writes_count
            )
            if found:
                return True, val, f"json:root/{src}"

            # Common nested dict: output["output"]
            inner = output.get("output")
            if isinstance(inner, dict):
                found, val, src = self._extract_from_mapping(
                    inner, write_key,
                    allow_singleton=True,
                    writes_count=writes_count
                )
                if found:
                    return True, val, f"json:nested_output/{src}"

            # Fallback: match by step-id suffix (e.g., _T004) when prefix diverges
            suffix_match = re.search(r"_t\d+$", write_key, flags=re.IGNORECASE)
            if suffix_match:
                suffix_norm = self._normalize_key(suffix_match.group(0))
                found, val, src = self._walk_find_key_suffix(output, suffix_norm)
                if found:
                    return True, val, f"json:suffix_match({src})"

        # Strategy 3: final_answer fallback (parse JSON hidden in text, or use raw text only if single write)
        final_ans = self._get_final_answer_field(output) if isinstance(output, dict) else None
        if final_ans is not None:
            found, val, src = self._extract_from_mapping(
                final_ans, write_key,
                allow_singleton=True,   # but scalar/text only becomes value when single write
                writes_count=writes_count
            )
            if found:
                return True, val, f"final_answer/{src}"

        return False, None, ""

    def _extract_executable_code(self, output):
        """
        Extracts executable code snippets from the agent's output.

        Args:
            output (dict): The agent's output.

        Returns:
            dict: A dictionary mapping code variants to code strings.
        """
        code_to_execute = {}

        if "code_variants" in output:
            for key, code in output["code_variants"].items():
                if isinstance(code, str):
                    code_to_execute[key] = code.strip()

        return code_to_execute

    async def _auto_execute_code(self, step_id, output):
        """
        Executes extracted code in the sandbox environment.
        Injects available global variables and agent outputs into the execution context.

        Args:
            step_id (str): The ID of the current step.
            output (dict): The agent's output containing code.

        Returns:
            dict: The result of the code execution.
        """
        code_to_execute = self._extract_executable_code(output)

        if not code_to_execute:
            return {"status": "error", "error": "No executable code found"}

        # Get node data for context
        node_data = self.plan_graph.nodes[step_id]
        reads = node_data.get("reads", [])

        # Get globals_schema for injection
        globals_schema = self.plan_graph.graph['globals_schema']

        for code_key, code in code_to_execute.items():
            try:
                # INJECT ALL AVAILABLE VARIABLES
                globals_injection = ""

                # 1. Inject ALL globals_schema variables
                for var_name, var_value in globals_schema.items():
                    # Parse stringified literals early (e.g. "['url1']" -> ['url1'])
                    parsed_value = self._ensure_parsed_value(var_value)
                    globals_injection += f'{var_name} = {repr(parsed_value)}\n'

                # 2. Inject agent's own output variables
                for var_name, var_value in output.items():
                    if var_name not in ['code_variants', 'call_self', 'cost', 'input_tokens', 'output_tokens', 'execution_result', 'execution_status', 'execution_error', 'execution_time', 'executed_variant']:
                        parsed_value = self._ensure_parsed_value(var_value)
                        globals_injection += f'{var_name} = {repr(parsed_value)}\n'

                # 3. Create convenience variables for reads
                reads_data = {}
                for read_key in reads:
                    if read_key in globals_schema:
                        reads_data[read_key] = self._ensure_parsed_value(globals_schema[read_key])

                globals_injection += f'reads_data = {repr(reads_data)}\n'

                enhanced_code = globals_injection + code

                result = await run_user_code(
                    enhanced_code,
                    self.multi_mcp if hasattr(self, 'multi_mcp') else None,
                    self.plan_graph.graph['session_id']
                )

                if result.get("status") == "success":
                    result["executed_variant"] = code_key
                    return result

            except Exception as e:
                continue

        return {"status": "error", "error": "All code variants failed"}

    def _merge_execution_results(self, original_output, execution_result):
        """
        Merges the results of code execution back into the agent's output dictionary.

        Args:
            original_output (dict): The original output from the agent.
            execution_result (dict): The result from the code execution.

        Returns:
            dict: The merged output dictionary.
        """
        if not isinstance(original_output, dict):
            return original_output

        enhanced_output = original_output.copy()
        enhanced_output["execution_result"] = execution_result.get("result")
        enhanced_output["execution_status"] = execution_result.get("status")
        enhanced_output["execution_error"] = execution_result.get("error")
        enhanced_output["execution_time"] = execution_result.get("execution_time")
        enhanced_output["executed_variant"] = execution_result.get("executed_variant")

        # Merge execution results directly
        if execution_result.get("status") == "success":
            result_data = execution_result.get("result", {})
            if isinstance(result_data, dict):
                for key, value in result_data.items():
                    if key not in enhanced_output:
                        enhanced_output[key] = value

        return enhanced_output

    def _is_clarification_request(self, agent_type, output):
        """
        Checks if the agent is requesting clarification from the user.

        Args:
            agent_type (str): The type of agent.
            output (dict): The agent's output.

        Returns:
            bool: True if a clarification is requested.
        """
        return (
            agent_type == "ClarificationAgent" and
            isinstance(output, dict) and
            "clarificationMessage" in output
        )

    def set_live_display(self, live_display):
        """
        Sets the reference to the Rich Live display, allowing it to be paused during user interaction.

        Args:
            live_display: The Rich Live display instance.
        """
        self._live_display = live_display

    def _handle_user_interaction_rich(self, clarification_output):
        """
        Handles interactive user input using Rich prompts.
        Pauses the live display if active.

        Args:
            clarification_output (dict): The output containing the clarification request.

        Returns:
            str: The user's response.
        """
        message = clarification_output.get("clarificationMessage", "")
        options = clarification_output.get("options", [])

        # Pause Live display during user interaction
        live_was_running = False
        if self._live_display and self._live_display._live_render.is_started:
            self._live_display.stop()
            live_was_running = True

        try:
            console = Console()
            console.clear()
            console.print(Panel(
                Text(message, style="bold white"),
                title="🤔 User Input Required",
                border_style="yellow",
                padding=(1, 2)
            ))

            if options:
                console.print("\n[bold cyan]Available Options:[/bold cyan]")
                for i, option in enumerate(options, 1):
                    console.print(f"  [bold white]{i}.[/bold white] {option}")

                choices = [str(i) for i in range(1, len(options) + 1)]
                choice = Prompt.ask(
                    "\n[bold green]Select option[/bold green]",
                    choices=choices,
                    default="1",
                    show_choices=False
                )

                selected_option = options[int(choice) - 1]
                console.print(f"[dim]✓ Selected: {selected_option}[/dim]")
                return selected_option
            else:
                response = Prompt.ask("\n[bold green]Your response[/bold green]")
                console.print(f"[dim]✓ Response: {response}[/dim]")
                return response

        finally:
            if live_was_running and self._live_display:
                self._live_display.start()

    async def mark_done(self, step_id, output=None, cost=None, input_tokens=None, output_tokens=None):
        """
        Marks a step as successfully completed.
        Handles data extraction, user interaction, and code execution results.
        Updates global variables and logs performance metrics.

        Args:
            step_id (str): The ID of the completed step.
            output (dict, optional): The output from the step.
            cost (float, optional): The cost of the step execution.
            input_tokens (int, optional): Number of input tokens.
            output_tokens (int, optional): Number of output tokens.
        """
        node_data = self.plan_graph.nodes[step_id]
        agent_type = node_data.get('agent', '')
        writes = node_data.get("writes", [])

        # Extract cost data
        if output and isinstance(output, dict):
            cost = cost or output.get('cost', 0.0)
            input_tokens = input_tokens or output.get('input_tokens', 0)
            output_tokens = output_tokens or output.get('output_tokens', 0)

        # USER INTERACTION CHECK
        if self._is_clarification_request(agent_type, output):
            try:
                raw_answer = self._handle_user_interaction_rich(output)
                writes_to = output.get("writes_to", "user_response")

                # Build rich context: Question + Answer
                question = (output.get("clarificationMessage") or "").strip()
                answer = raw_answer.strip() if isinstance(raw_answer, str) else str(raw_answer)
                if not question:
                    question = f"Clarification requested by {agent_type or 'agent'}"

                rich_context = f"Agent asked: {question} User said: {answer}"

                globals_schema = self.plan_graph.graph['globals_schema']

                # Save rich context into the primary memory slot (fix for "Amnesic User")
                globals_schema[writes_to] = rich_context

                # Also keep structured pieces for downstream code/prompting if needed
                globals_schema[f"{writes_to}_raw"] = answer
                globals_schema[f"{writes_to}_question"] = question

                output = output.copy()

                # Ensure extraction logic later in mark_done picks up rich context
                output[writes_to] = rich_context
                output[f"{writes_to}_raw"] = answer
                output[f"{writes_to}_question"] = question

                # Convenience / legacy keys
                output["user_response"] = rich_context
                output["user_response_raw"] = answer
                output["clarification_question"] = question
                output["rich_context"] = rich_context
                output["interaction_completed"] = True

                print(f"✅ User input captured: {writes_to} = '{rich_context}'")

            except Exception as e:
                print(f"❌ User interaction failed: {e}")

        # CODE EXECUTION CHECK
        execution_result = None
        if self._has_executable_code(output):
            try:
                execution_result = await self._auto_execute_code(step_id, output)
                output = self._merge_execution_results(output, execution_result)
            except Exception as e:
                print(f"❌ Code execution failed: {e}")

        # EXTRACTION LOGIC - Handle both code execution results AND direct agent outputs
        globals_schema = self.plan_graph.graph['globals_schema']

        if writes:
            for write_key in writes:
                found, value, source = self._extract_write_value(
                    write_key,
                    writes=writes,
                    output=output,
                    execution_result=execution_result
                )

                if found:
                    # Normalize/parse before storing so all downstream consumers
                    # (including sandbox injection) see correct Python types.
                    parsed_value = self._ensure_parsed_value(value)
                    globals_schema[write_key] = parsed_value
                    print(f"✅ Extracted {write_key} = {self._short_repr(parsed_value)} ({source})")
                else:
                    print(f"⚠️  Could not extract {write_key}")
                    # Keep existing behavior: safe placeholder prevents downstream breakage
                    globals_schema[write_key] = []

        # Store results
        node_data['status'] = 'completed'
        node_data['end_time'] = datetime.utcnow().isoformat()
        node_data['output'] = output
        node_data['cost'] = cost or 0.0
        node_data['input_tokens'] = input_tokens or 0
        node_data['output_tokens'] = output_tokens or 0
        node_data['total_tokens'] = (input_tokens or 0) + (output_tokens or 0)

        # Calculate execution time
        if 'start_time' in node_data and node_data['start_time']:
            start = datetime.fromisoformat(node_data['start_time'])
            end = datetime.fromisoformat(node_data['end_time'])
            node_data['execution_time'] = (end - start).total_seconds()

        print(f"✅ {step_id} completed successfully")
        self._auto_save()

    def mark_failed(self, step_id, error=None):
        """
        Marks a step as failed and records the error.

        Args:
            step_id (str): The ID of the failed step.
            error (Any, optional): The error object or message.
        """
        node_data = self.plan_graph.nodes[step_id]
        node_data['status'] = 'failed'
        node_data['end_time'] = datetime.utcnow().isoformat()
        node_data['error'] = str(error) if error else None

        if node_data['start_time']:
            start = datetime.fromisoformat(node_data['start_time'])
            end = datetime.fromisoformat(node_data['end_time'])
            node_data['execution_time'] = (end - start).total_seconds()

        self._auto_save()

    def get_step_data(self, step_id):
        """
        Retrieves data for a specific step from the graph.

        Args:
            step_id (str): The step ID.

        Returns:
            dict: The node data.
        """
        return self.plan_graph.nodes[step_id]

    def get_inputs(self, reads):
        """
        Retrieves input values from the global schema based on read keys.

        Args:
            reads (list): List of keys to read.

        Returns:
            dict: A dictionary of retrieved input values.
        """
        inputs = {}
        globals_schema = self.plan_graph.graph['globals_schema']

        for read_key in reads:
            if read_key in globals_schema:
                inputs[read_key] = self._ensure_parsed_value(globals_schema[read_key])
            else:
                print(f"⚠️  Missing dependency: '{read_key}' not found in globals_schema")
                print(f"📋 Available keys: {list(globals_schema.keys())}")

        return inputs

    def all_done(self):
        """
        Checks if all steps in the graph have either completed or failed.

        Returns:
            bool: True if all steps are done.
        """
        return all(
            self.plan_graph.nodes[node_id]['status'] in ['completed', 'failed']
            for node_id in self.plan_graph.nodes
        )

    def get_execution_summary(self):
        """
        Generates a summary of the execution, including costs, tokens, and final outputs.

        Returns:
            dict: The execution summary.
        """
        completed = sum(1 for node_id in self.plan_graph.nodes
                       if node_id != "ROOT" and
                       self.plan_graph.nodes[node_id].get('status') == 'completed')
        failed = sum(1 for node_id in self.plan_graph.nodes
                    if node_id != "ROOT" and
                    self.plan_graph.nodes[node_id].get('status') == 'failed')
        total = len(self.plan_graph.nodes) - 1

        # Calculate costs
        total_cost = 0.0
        total_input_tokens = 0
        total_output_tokens = 0
        cost_breakdown = {}

        for node_id in self.plan_graph.nodes:
            if node_id != "ROOT":
                node_data = self.plan_graph.nodes[node_id]
                node_cost = node_data.get('cost', 0.0)
                node_input_tokens = node_data.get('input_tokens', 0)
                node_output_tokens = node_data.get('output_tokens', 0)

                if node_cost > 0:
                    agent = node_data.get('agent', 'Unknown')
                    cost_breakdown[f"{node_id} ({agent})"] = {
                        "cost": node_cost,
                        "input_tokens": node_input_tokens,
                        "output_tokens": node_output_tokens
                    }

                total_cost += node_cost
                total_input_tokens += node_input_tokens
                total_output_tokens += node_output_tokens

        # Get final outputs
        final_outputs = {}
        all_reads = set()
        all_writes = set()

        for node_id in self.plan_graph.nodes:
            node_data = self.plan_graph.nodes[node_id]
            all_reads.update(node_data.get("reads", []))
            all_writes.update(node_data.get("writes", []))

        final_write_keys = all_writes - all_reads
        globals_schema = self.plan_graph.graph['globals_schema']
        for key in final_write_keys:
            if key in globals_schema:
                final_outputs[key] = globals_schema[key]

        return {
            "session_id": self.plan_graph.graph['session_id'],
            "original_query": self.plan_graph.graph['original_query'],
            "completed_steps": completed,
            "failed_steps": failed,
            "total_steps": total,
            "total_cost": total_cost,
            "total_input_tokens": total_input_tokens,
            "total_output_tokens": total_output_tokens,
            "total_tokens": total_input_tokens + total_output_tokens,
            "cost_breakdown": cost_breakdown,
            "final_outputs": final_outputs,
            "globals_schema": globals_schema
        }

    def set_file_profiles(self, file_profiles):
        """
        Stores file profile information in the graph.

        Args:
            file_profiles (dict): The file profiles to store.
        """
        self.plan_graph.graph['file_profiles'] = file_profiles

    def set_multi_mcp(self, multi_mcp):
        """
        Sets the MultiMCP reference used for code execution.

        Args:
            multi_mcp: The MultiMCP instance.
        """
        self.multi_mcp = multi_mcp

    def _auto_save(self):
        """
        Triggers an auto-save of the session state.
        Skipped in debug mode.
        """
        if self.debug_mode:
            return
        try:
            self._save_session()
        except Exception as e:
            print(f"⚠️  Auto-save failed: {e}")

    def _save_session(self):
        """
        Saves the current state of the NetworkX graph to a JSON file.
        """
        base_dir = Path(__file__).parent.parent / "memory" / "session_summaries_index"
        today = datetime.now()
        date_dir = base_dir / str(today.year) / f"{today.month:02d}" / f"{today.day:02d}"
        date_dir.mkdir(parents=True, exist_ok=True)

        session_id = self.plan_graph.graph['session_id']
        session_file = date_dir / f"session_{session_id}.json"

        graph_data = nx.node_link_data(self.plan_graph)

        with open(session_file, 'w', encoding='utf-8') as f:
            json.dump(graph_data, f, indent=2, default=str, ensure_ascii=False)

    @classmethod
    def load_session(cls, session_file: Path, debug_mode: bool = False):
        """
        Loads a session from a JSON file and reconstructs the ExecutionContextManager.

        Args:
            session_file (Path): Path to the session file.
            debug_mode (bool, optional): Whether to enable debug mode. Defaults to False.

        Returns:
            ExecutionContextManager: The reconstructed context manager.
        """
        with open(session_file, 'r', encoding='utf-8') as f:
            graph_data = json.load(f)

        plan_graph = nx.node_link_graph(graph_data, edges="links")

        context = cls.__new__(cls)
        context.plan_graph = plan_graph
        context.debug_mode = debug_mode
        return context
