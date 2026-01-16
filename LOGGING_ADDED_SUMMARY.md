# Comprehensive Logging Added to Web Search System

**Date**: 2026-01-10
**File Modified**: `mcp_servers/tools/switch_search_method.py`

---

## Overview

Added detailed diagnostic logging at every level of the web search system to identify why searches are returning empty results despite successful HTTP responses.

---

## Logging Added by Function

### 1. `smart_search()` - Main Orchestrator (lines 309-377)

**Purpose**: Track the overall search flow across multiple engines

**Logs Added**:
- 🔍 Search start banner with query and limit
- 🎲 Engine execution order
- 🚀 Each attempt with engine name and attempt number
- ⏱️ Timeout values for each engine
- ✅ Results count from each engine
- 🎉 Success with final URL list
- ❌ All engines failed summary
- Full traceback on exceptions

**Example Output**:
```
================================================================================
🔍 SMART_SEARCH: Starting search orchestration
📝 Query: 'Dhurandhar Movie revenue box office'
📊 Requested limit: 5
================================================================================

🎲 SMART_SEARCH: Engine order: ['duck_http', 'bing_playwright', 'ecosia_playwright', ...]

────────────────────────────────────────────────────────────────────────────────
🚀 SMART_SEARCH: Attempt 1/6 - Trying engine: duck_http
────────────────────────────────────────────────────────────────────────────────
```

---

### 2. `use_duckduckgo_http()` - HTTP Search (lines 85-180)

**Purpose**: Diagnose HTML parsing and selector issues

**Logs Added**:
- 🔍 Query being searched
- 📡 Request URL and User-Agent
- ✅ HTTP status code
- 📄 Response content length
- 🔗 Final URL after redirects
- 📋 HTML preview (first 800 characters)
- ⚠️ Anti-bot indicators detection (CAPTCHA, unusual traffic, JavaScript required)
- 🔎 Testing 4 different CSS selectors with counts
- 🎯 Primary selector results count
- Per-link processing:
  - Raw href value
  - ❌ Empty href detection
  - 🔓 uddg parameter decoding
  - ✅ Successfully added URLs
  - ⏭️ Skip reasons (duplicate, not http)
- 📊 Final result count
- 💾 Save full HTML to `/tmp/duckduckgo_debug_*.html` when empty

**Selectors Tested**:
1. `a.result__a` (current selector)
2. `div.result__body a` (alternative)
3. `a[class*='result']` (wildcard)
4. `div[class*='result'] a` (broader wildcard)

**Example Output**:
```
[duck_http] 🔍 Searching for: 'Dhurandhar Movie revenue box office'
[duck_http] 📡 Request URL: https://html.duckduckgo.com/html
[duck_http] 🎭 User-Agent: Mozilla/5.0 (Windows NT 10.0; Win64...
[duck_http] ✅ HTTP Status: 200
[duck_http] 📄 Response length: 45823 characters
[duck_http] 📋 HTML Preview (first 800 chars):
<!DOCTYPE html><html lang="en">...

[duck_http] 🔎 Testing 4 different selectors...
[duck_http]    - 'a.result__a': 0 elements found
[duck_http]    - 'div.result__body a': 0 elements found
[duck_http]    - 'a[class*='result']': 0 elements found
[duck_http]    - 'div[class*='result'] a': 0 elements found

[duck_http] 🎯 Using primary selector 'a.result__a': 0 elements
[duck_http] 📊 Final result: 0 unique URLs extracted
[duck_http] ⚠️  No links found in results - possible parsing failure
[duck_http] 💾 Saved full HTML response to: /tmp/duckduckgo_debug_1736545812.html
```

---

### 3. `use_playwright_search()` - Browser Search (lines 182-307)

**Purpose**: Track headless browser operations and element selection

**Logs Added**:
- 🌐 Browser search start
- 🚀 Browser launch confirmation
- 🔗 Navigation URL
- ✅ Page load success
- 🔍 Selector being used for each engine
- 📊 Elements found count
- ⚠️ Retry attempts if initial query fails
- 🔄 Retry results count
- Per-link processing (same as HTTP function):
  - Raw href
  - Empty detection
  - uddg decoding
  - Added/skipped with reasons
  - ❌ Errors with full details
- 🔒 Browser closed
- 📊 Final result count
- Full traceback on exceptions

**Example Output**:
```
[duck_playwright] 🌐 Starting Playwright browser search for: 'Dhurandhar Movie revenue box office'
[duck_playwright] 🚀 Browser launched, page created
[duck_playwright] 🔗 Navigating to https://html.duckduckgo.com/html?q=Dhurandhar+Movie+revenue+box+office
[duck_playwright] ✅ Page loaded, waiting 2 seconds for JS...
[duck_playwright] 🔍 Waiting for selector 'a.result__a'...
[duck_playwright] 📊 Found 10 result elements
[duck_playwright]    [1] Raw href: //duckduckgo.com/l/?uddg=https%3A%2F%2Fwww.example.com%2F...
[duck_playwright]    [1] 🔓 Decoded uddg: https://www.example.com/...
[duck_playwright]    [1] ✅ Added: https://www.example.com/...
```

---

## Diagnostic Features

### 1. Anti-Bot Detection
Checks HTML response for common bot-blocking indicators:
- CAPTCHA challenges
- "Unusual traffic" messages
- JavaScript enable requirements

### 2. Multiple Selector Testing
Tests 4 different CSS selectors to identify if HTML structure changed

### 3. HTML Debug Dump
Saves full HTML response to `/tmp/duckduckgo_debug_*.html` when no results found

### 4. Full Error Tracebacks
Complete stack traces printed for all exceptions

### 5. Per-Link Processing Visibility
Shows exactly why each link was added or skipped

---

## How to Use This Logging

### When Running a Search:

1. **Check stderr output** - All logs go to stderr (not stdout)

2. **Look for these key indicators**:
   - ✅ HTTP 200 but 0 elements found → HTML structure changed
   - ⚠️ CAPTCHA detected → Bot blocking active
   - 🔎 All selectors return 0 → Major HTML change
   - 📄 Response length < 5000 → Likely redirect/error page

3. **Examine the debug HTML file**:
   ```bash
   ls -lt /tmp/duckduckgo_debug_*.html | head -1
   cat /tmp/duckduckgo_debug_1736545812.html
   ```

4. **Trace the full flow**:
   - SMART_SEARCH shows which engines were tried
   - Each engine shows detailed processing
   - Success/failure clearly marked

---

## Expected Output Structure

```
SMART_SEARCH banner
├── Engine attempt 1: duck_http
│   ├── HTTP request details
│   ├── Response analysis
│   ├── Selector testing
│   ├── Link extraction
│   └── Results summary
├── Engine attempt 2: bing_playwright
│   ├── Browser launch
│   ├── Page navigation
│   ├── Element selection
│   └── Results summary
└── Final result/failure

Total: ~50-100 log lines per search depending on results
```

---

## Files to Check for Debugging

1. **stderr output** - Main log stream
2. `/tmp/duckduckgo_debug_*.html` - Full HTML responses when search fails
3. MCP server logs - Any tool execution errors

---

## Next Steps After Analyzing Logs

Based on log output, you can:

1. **If selectors return 0**: Update CSS selectors in code
2. **If CAPTCHA detected**: Switch to Playwright engines faster
3. **If response is small**: Check for redirects or blocks
4. **If uddg decoding fails**: Update URL extraction logic
5. **If all engines fail**: Network/firewall issue or regional blocking

---

**End of Summary**
