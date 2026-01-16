
from mcp.server.fastmcp import FastMCP, Context
import httpx
from bs4 import BeautifulSoup
from typing import List, Dict, Optional, Any
from dataclasses import dataclass
import urllib.parse
import sys
import traceback
from datetime import datetime
import asyncio
import os
from dotenv import load_dotenv

# Browser Use Imports
try:
    from browser_use import Agent
    from langchain_google_genai import ChatGoogleGenerativeAI
    BROWSER_USE_AVAILABLE = True
except ImportError:
    BROWSER_USE_AVAILABLE = False
    sys.stderr.write("⚠️ browser-use not installed. Vision features will be disabled.\n")

load_dotenv()

# Initialize FastMCP server
mcp = FastMCP("hybrid-browser")

# --- Tool 1: Fast Text Search (DuckDuckGo + Extraction) ---

# --- Robust Tools Imports ---
try:
    from tools.switch_search_method import smart_search
    from tools.web_tools_async import smart_web_extract
except ImportError:
    # Try relative import if running as module
    from .tools.switch_search_method import smart_search
    from .tools.web_tools_async import smart_web_extract

# --- Tool 1: Fast Robust Search (DuckDuckGo + Fallbacks) ---

@mcp.tool()
async def web_search(string: str, integer: int = 5) -> List[str]:
    """
    Search the web using multiple engines (DuckDuckGo, Bing, Ecosia, etc.)
    and return a list of relevant result URLs.

    IMPORTANT: Returns a Python list[str]. On any error (or empty query), returns [].
    """
    try:
        query = (string or "").strip()
        if not query:
            sys.stderr.write("⚠️ web_search called with empty query; returning [].\n")
            sys.stderr.flush()
            return []

        try:
            max_results = int(integer)
        except (TypeError, ValueError):
            max_results = 5

        # Clamp to prevent abuse / runaway latency
        max_results = max(1, min(max_results, 20))

        # Hard timeout to avoid hanging MCP calls
        urls = await asyncio.wait_for(smart_search(query, max_results), timeout=25)
        if not isinstance(urls, list):
            sys.stderr.write("⚠️ smart_search returned non-list; returning [].\n")
            sys.stderr.flush()
            return []

        urls = [u for u in urls if isinstance(u, str) and u.strip()]
        if not urls:
            sys.stderr.write(f"⚠️ web_search: no results for query={query!r}\n")
            sys.stderr.flush()
        return urls
    except asyncio.TimeoutError:
        sys.stderr.write("⚠️ web_search timed out; returning [].\n")
        sys.stderr.flush()
        return []
    except Exception as e:
        traceback.print_exc()
        sys.stderr.write(f"⚠️ web_search failed: {str(e)}; returning [].\n")
        sys.stderr.flush()
        return []

@mcp.tool()
async def web_extract_text(string: str) -> str:
    """Extract readable text from a webpage using robust methods (Playwright/Trafilatura)."""
    try:
        # Timeout 45s for robust extraction
        result = await asyncio.wait_for(smart_web_extract(string), timeout=45)
        text = result.get("best_text", "")[:15000] # Increased limit
        return text if text else "[Error] No text extracted"
    except Exception as e:
        return f"[Error] Extraction failed: {str(e)}"

# --- Tool 2: Deep Vision Browsing (Browser Use) ---

@mcp.tool()
async def browser_use_action(string: str, headless: bool = True) -> str:
    """
    Execute a complex browser task using Vision and generic reasoning.
    Use this for: Logging in, filling forms, navigating complex sites, or when text search fails.
    WARNING: Slow and expensive.
    """
    if not BROWSER_USE_AVAILABLE:
        return "Error: `browser-use` library is not installed."

    try:
        # Initialize LLM
        llm = ChatGoogleGenerativeAI(model="gemini-2.0-flash", google_api_key=os.getenv("GEMINI_API_KEY"))
        
        # Initialize Agent
        agent = Agent(
            task=string,
            llm=llm,
        )
        
        # Run
        history = await agent.run()
        result = history.final_result()
        return result if result else "Task completed but returned no text result."

    except Exception as e:
        traceback.print_exc()
        return f"Browser Action Failed: {str(e)}"

if __name__ == "__main__":
    print("hybrid-browser server READY")
    mcp.run(transport="stdio")
