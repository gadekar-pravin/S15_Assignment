# BUG REPORT: Web Search Returning Empty Results

**Date**: 2026-01-10
**Severity**: HIGH
**Status**: OPEN
**Reporter**: System Analysis

---

## Executive Summary

The `web_search()` MCP tool is successfully executing HTTP requests (returning 200 OK) but consistently returning empty result lists to the RetrieverAgent. This causes retrieval tasks to fail silently while being marked as "completed successfully."

---

## Problem Description

### Observed Behavior

When RetrieverAgent calls `web_search()` to find information:
1. HTTP request succeeds (DuckDuckGo returns 200 OK)
2. Function returns but agent receives empty list
3. Task marked as "✅ completed successfully" despite finding no data
4. No error messages or warnings generated

### Expected Behavior

1. `web_search()` should return a list of URLs from successful searches
2. Task should fail or retry if no results found
3. Error logging should indicate when search yields no results

---

## Root Cause Analysis

### Primary Issue: Return Type Mismatch

**Location**: `mcp_servers/server_browser.py:44-73`

The `web_search()` function returns a **JSON string**:
```python
return json.dumps(
    {"ok": True, "query": query, "max_results": max_results, "urls": urls},
    ensure_ascii=False
)
```

However, the agent-generated code expects a **list of URLs**:
```python
urls = web_search('"Dhurandhar" movie revenue box office', 5)
if not isinstance(urls, list): urls = []  # <-- This triggers, setting urls = []
```

**Why This Happens**:
- `web_search()` returns: `'{"ok": true, "urls": ["http://..."]}'` (string)
- Agent checks: `isinstance(urls, list)` → False (it's a string)
- Agent sets: `urls = []` (empty list)
- Result: Empty data, but no error thrown

### Secondary Issue: Silent Failure Acceptance

**Locations**:
- `agents/base_agent.py:133-137`
- Agent executor (runtime)

Tasks are marked successful based solely on code execution without validating:
- Whether tool calls returned meaningful data
- Whether task objectives were achieved
- Whether output variables contain expected values

---

## Impacted Components

### Critical Files Requiring Updates

1. **`mcp_servers/server_browser.py`** (lines 43-73)
   - **Issue**: Returns JSON string instead of Python list
   - **Fix Required**: Parse JSON or change return type
   - **Priority**: HIGH

2. **`prompts/retriever.md`**
   - **Issue**: Agent prompt doesn't specify tool return format
   - **Fix Required**: Document that `web_search()` returns JSON string
   - **Priority**: HIGH

3. **`tools/sandbox.py`** (lines 125-400, function execution area)
   - **Issue**: No automatic JSON parsing for MCP tool results
   - **Fix Required**: Add JSON deserialization for tools that return JSON
   - **Priority**: HIGH

4. **`agents/base_agent.py`** (lines 133-137)
   - **Issue**: Marks tasks successful without output validation
   - **Fix Required**: Add result validation logic
   - **Priority**: MEDIUM

5. **`core/loop.py`** (execution flow)
   - **Issue**: No task objective validation
   - **Fix Required**: Check if task goals met before marking complete
   - **Priority**: MEDIUM

6. **`mcp_servers/tools/switch_search_method.py`** (lines 220-259)
   - **Issue**: `smart_search()` correctly returns list, but wrapper converts to JSON
   - **Fix Required**: Ensure consistent return types throughout call chain
   - **Priority**: LOW

---

## Reproduction Steps

1. Execute any RetrieverAgent task with web search requirement
2. Observe runtime log showing:
   ```
   urls = web_search('"Dhurandhar" movie revenue box office', 5)
   HTTP Request: POST https://html.duckduckgo.com/html "HTTP/1.1 200 OK"
   dhurandhar_revenue_data_T001: []  # <-- Empty result
   ✅ T001 completed successfully     # <-- Incorrectly marked as success
   ```

---

## Recommended Solutions

### Option 1: Change Tool Return Type (Recommended)

**Pros**: Simplest fix, maintains agent code compatibility
**Cons**: Loses error information in return value

**Implementation**:
```python
# mcp_servers/server_browser.py, line 44
@mcp.tool()
async def web_search(string: str, integer: int = 5) -> list:  # Change return type
    """Search the web and return a list of URLs"""
    try:
        # ... existing logic ...
        urls = await asyncio.wait_for(smart_search(query, max_results), timeout=25)
        return urls  # Return list directly, not JSON
    except Exception as e:
        traceback.print_exc()
        return []  # Return empty list on error
```

### Option 2: Add JSON Parsing in Sandbox Executor

**Pros**: Maintains JSON error handling, backward compatible
**Cons**: More complex, requires updating multiple components

**Implementation**:
```python
# tools/sandbox.py, after tool call execution
def parse_tool_result(result, tool_name):
    """Parse JSON results from MCP tools"""
    if isinstance(result, str):
        try:
            parsed = json.loads(result)
            # If it's a web_search result, extract URLs
            if tool_name == "web_search" and isinstance(parsed, dict):
                return parsed.get("urls", [])
            return parsed
        except json.JSONDecodeError:
            return result
    return result
```

### Option 3: Update Agent Prompt to Parse JSON

**Pros**: Allows agents to handle errors explicitly
**Cons**: Increases agent code complexity, relies on LLM correctness

**Implementation**:
```markdown
# prompts/retriever.md
### Tool Return Formats

- `web_search(query, limit)`: Returns JSON string: {"ok": bool, "urls": list[str], "error": str}

  **Usage**:
  ```python
  import json
  result = json.loads(web_search("query", 5))
  if result["ok"]:
      urls = result["urls"]
  else:
      print(f"Error: {result['error']}")
  ```
```

---

## Additional Issues Found

### 1. No Result Validation
Tasks marked complete even when primary objective fails (no data retrieved).

**Fix**: Add validation in `core/loop.py` to check if expected output variables contain data.

### 2. No Error Propagation
Silent failures don't trigger retries or alternative strategies.

**Fix**: Implement retry logic in `mcp_servers/tools/switch_search_method.py` when result list is empty.

### 3. Misleading Success Messages
Logs show "✅ completed successfully" when task objectively failed.

**Fix**: Distinguish between "code executed" vs "objective achieved" in status messages.

---

## Testing Requirements

After implementing fixes, verify:

1. ✅ `web_search()` returns non-empty results for valid queries
2. ✅ Agent code correctly receives and processes URL lists
3. ✅ Empty results trigger appropriate error handling
4. ✅ Tasks only marked successful when data is retrieved
5. ✅ Error messages clearly indicate search failures
6. ✅ Retry mechanisms activate when initial search fails

---

## Impact Assessment

- **User Impact**: HIGH - Core retrieval functionality broken
- **Data Quality**: HIGH - Empty results marked as successful lead to incomplete task execution
- **Debugging Difficulty**: HIGH - Silent failures make issues hard to trace
- **Production Readiness**: CRITICAL - Must be fixed before deployment

---

## Related Files for Reference

### Configuration
- `config/agent_config.yaml` - Agent definitions and MCP server mappings

### Core Execution
- `app.py` - Main application entry point
- `memory/context.py` - Execution context management

### Agent System
- `prompts/planner.md` - Planner agent prompt
- `prompts/clarification.md` - Clarification agent prompt
- `prompts/browser.md` - Browser agent prompt

---

## Appendix: Runtime Log Extract

```
🚀 🔄 Starting T001 (RetrieverAgent): Find the most recent and reliable revenue data...
🔄 🔄 RetrieverAgent Iteration 1/15

🐍 [CODE:]: result_variable_T001 = []
total_tokens = 82
reads_data = {}
urls = web_search('"Dhurandhar" movie revenue box office', 5)
if not isinstance(urls, list): urls = []
return {'dhurandhar_revenue_data_T001': urls}

[01/10/26 22:44:58] INFO Processing request of type CallToolRequest
Trying engine: duck_http
[01/10/26 22:44:59] INFO HTTP Request: POST https://html.duckduckgo.com/html "HTTP/1.1 200 OK"

╭─ 📌 Executor result ──────────╮
│ dhurandhar_revenue_data_T001: │  <-- EMPTY!
╰───────────────────────────────╯

✅ Extracted dhurandhar_revenue_data_T001 = []
✅ T001 completed successfully  <-- INCORRECT STATUS
```

---

## Next Steps

1. **Immediate**: Assign to backend team for triage
2. **Priority**: Implement Option 1 (simplest fix)
3. **Follow-up**: Add result validation logic
4. **Testing**: Create integration test suite for MCP tools
5. **Documentation**: Update API docs with correct return types

---

**End of Report**
