from app import AgentLoop4
from mcp_servers.multi_mcp import MultiMCP
import asyncio
from rich.console import Console

async def main():
    """
    Runs a test scenario focused on investment research.
    Queries for startup investments in India and expects a markdown report.
    This test verifies the system's ability to handle research, data aggregation, and formatting.
    """
    multi_mcp = MultiMCP()
    console = Console()
    
    try:
        print("🚀 Starting MCP Servers...")
        await multi_mcp.start()
        
        loop = AgentLoop4(multi_mcp)
        
        query = "Find the major investments that happened in startups in India in last 15 days (from Dec 1 2025 to 15th December 2025), and give me a beautifully drafted report in markdown file"
        
        print(f"TEST: Running query: {query}\n")
        
        context = await loop.run(
            query=query,
            file_manifest={},
            globals_schema={},
            uploaded_files=[]  # No files for this test
        )
        
        # Validation
        print("\nTEST COMPLETE. Summary:")
        graph_globals = context.plan_graph.graph.get('globals_schema', {})
        print(f"Global Schema Keys: {list(graph_globals.keys())}")
        
    except Exception as e:
        print(f"TEST FAILED: {e}")
        import traceback
        traceback.print_exc()
    finally:
        print("🛑 Stopping MCP Servers...")
        await multi_mcp.stop()

if __name__ == "__main__":
    asyncio.run(main())
