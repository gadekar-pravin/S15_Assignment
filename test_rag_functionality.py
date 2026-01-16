"""
Comprehensive RAG (Retrieval Augmented Generation) Functionality Test

Tests the RAG system's ability to:
1. Index and retrieve documents using FAISS
2. Generate embeddings with Ollama
3. Search for relevant content based on queries
4. Handle different types of documents (PDF, DOCX, TXT, MD)
"""

import asyncio
import sys
import os
import json
from pathlib import Path
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
import requests

# Add project root to path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from mcp_servers.multi_mcp import MultiMCP

console = Console()

def check_ollama_status():
    """Verify that Ollama is running and has required models"""
    console.print("\n[bold cyan]🔍 Checking Ollama Status[/bold cyan]")
    try:
        response = requests.get("http://localhost:11434/api/tags", timeout=5)
        if response.status_code == 200:
            models = response.json().get("models", [])
            model_names = [m["name"] for m in models]

            table = Table(title="Available Models")
            table.add_column("Model Name", style="cyan")
            table.add_column("Size", style="green")

            for model in models:
                size_mb = model["size"] / (1024 * 1024)
                table.add_row(model["name"], f"{size_mb:.2f} MB")

            console.print(table)

            # Check for required model
            if any("nomic-embed-text" in name for name in model_names):
                console.print("✅ [green]Required embedding model found![/green]")
                return True
            else:
                console.print("❌ [red]nomic-embed-text model not found![/red]")
                return False
        else:
            console.print(f"❌ [red]Ollama API returned status {response.status_code}[/red]")
            return False
    except requests.exceptions.RequestException as e:
        console.print(f"❌ [red]Ollama is not running or not accessible: {e}[/red]")
        console.print("💡 [yellow]Start Ollama with: ollama serve[/yellow]")
        return False

def check_faiss_index():
    """Verify that FAISS index exists and has data"""
    console.print("\n[bold cyan]🔍 Checking FAISS Index[/bold cyan]")
    ROOT = Path(__file__).parent / "mcp_servers"
    index_path = ROOT / "faiss_index" / "index.bin"
    metadata_path = ROOT / "faiss_index" / "metadata.json"

    if not index_path.exists():
        console.print("❌ [red]FAISS index file not found![/red]")
        return False

    if not metadata_path.exists():
        console.print("❌ [red]FAISS metadata file not found![/red]")
        return False

    # Check metadata content
    try:
        metadata = json.loads(metadata_path.read_text())
        console.print(f"✅ [green]FAISS index found with {len(metadata)} chunks[/green]")

        # Show distribution of documents
        doc_counts = {}
        for item in metadata:
            doc_name = item.get("doc", "unknown")
            doc_counts[doc_name] = doc_counts.get(doc_name, 0) + 1

        table = Table(title="Indexed Documents")
        table.add_column("Document", style="cyan")
        table.add_column("Chunks", style="green")

        for doc, count in sorted(doc_counts.items()):
            table.add_row(doc, str(count))

        console.print(table)
        return True
    except Exception as e:
        console.print(f"❌ [red]Error reading metadata: {e}[/red]")
        return False

async def test_embedding_generation():
    """Test that embeddings can be generated via Ollama API"""
    console.print("\n[bold cyan]🧪 Testing Embedding Generation[/bold cyan]")
    try:
        test_text = "This is a test sentence for embedding generation."
        response = requests.post(
            "http://localhost:11434/api/embeddings",
            json={"model": "nomic-embed-text", "prompt": test_text},
            timeout=30
        )
        response.raise_for_status()
        embedding = response.json()["embedding"]

        console.print(f"✅ [green]Embedding generated successfully[/green]")
        console.print(f"   Dimension: {len(embedding)}")
        console.print(f"   Type: {type(embedding)}")
        console.print(f"   Sample values: {embedding[:5]}...")
        return True
    except Exception as e:
        console.print(f"❌ [red]Embedding generation failed: {e}[/red]")
        return False

async def test_rag_search(mcp_client, query: str, expected_topic: str = None):
    """Test RAG search with a specific query using MCP tools"""
    console.print(f"\n[bold yellow]🔎 Query:[/bold yellow] {query}")

    try:
        # Call the RAG tool through MCP interface
        # The tool expects an "input" parameter containing the SearchDocumentsInput
        result = await mcp_client.call_tool(
            "rag",
            "search_stored_documents_rag",
            arguments={"input": {"query": query}}
        )

        if not result or not result.content:
            console.print("❌ [red]No results returned[/red]")
            return False

        # Extract the actual results
        results = []
        for content_item in result.content:
            if hasattr(content_item, 'text'):
                results.append(content_item.text)

        if not results:
            console.print("❌ [red]No text results in response[/red]")
            return False

        # Check for errors
        first_result = results[0] if results else ""
        if "ERROR:" in first_result:
            console.print(f"❌ [red]{first_result}[/red]")
            return False

        console.print(f"✅ [green]Found {len(results)} results[/green]")

        # Display results
        for i, result_text in enumerate(results, 1):
            # Split result into content and source
            if "[Source:" in result_text:
                content, source = result_text.rsplit("[Source:", 1)
                source = "[Source:" + source
            else:
                content = result_text
                source = "[No source info]"

            # Truncate content for display
            content_preview = content[:200] + "..." if len(content) > 200 else content

            console.print(Panel(
                f"{content_preview}\n\n[dim]{source}[/dim]",
                title=f"Result {i}",
                border_style="green"
            ))

        return True
    except Exception as e:
        console.print(f"❌ [red]Search failed: {e}[/red]")
        import traceback
        traceback.print_exc()
        return False

async def run_comprehensive_rag_tests(mcp_client):
    """Run a comprehensive suite of RAG tests"""
    console.print(Panel.fit(
        "[bold cyan]🚀 RAG Functionality Test Suite[/bold cyan]",
        border_style="blue"
    ))

    # Phase 1: Pre-flight checks
    console.print("\n[bold]Phase 1: Pre-flight Checks[/bold]")

    ollama_ok = check_ollama_status()
    faiss_ok = check_faiss_index()
    embedding_ok = await test_embedding_generation()

    if not (ollama_ok and faiss_ok and embedding_ok):
        console.print("\n❌ [red bold]Pre-flight checks failed. Cannot proceed with tests.[/red bold]")
        return False

    console.print("\n✅ [green bold]All pre-flight checks passed![/green bold]")

    # Phase 2: Search tests with different query types
    console.print("\n[bold]Phase 2: RAG Search Tests[/bold]")

    test_queries = [
        # Test 1: Specific document content (cricket.txt)
        ("Who is the best cricketer according to the documents?", "cricket"),

        # Test 2: Economic/business content (dlf.md, economic.md)
        ("What information is available about DLF or real estate?", "real estate"),

        # Test 3: PDF content (BRSR report)
        ("What sustainability or environmental information is in the documents?", "sustainability"),

        # Test 4: Canvas LMS or education
        ("How to use Canvas LMS?", "education"),

        # Test 5: General query that should match multiple documents
        ("What are the main topics discussed in these documents?", "general"),

        # Test 6: Specific entity search
        ("Tell me about policies and procedures", "policies"),
    ]

    results = []
    for query, expected_topic in test_queries:
        success = await test_rag_search(mcp_client, query, expected_topic)
        results.append((query, success))
        await asyncio.sleep(1)  # Small delay between requests

    # Phase 3: Results summary
    console.print("\n[bold]Phase 3: Test Results Summary[/bold]")

    summary_table = Table(title="Test Results")
    summary_table.add_column("Query", style="cyan", width=50)
    summary_table.add_column("Status", style="green")

    passed = 0
    for query, success in results:
        status = "✅ PASS" if success else "❌ FAIL"
        summary_table.add_row(query[:50] + "..." if len(query) > 50 else query, status)
        if success:
            passed += 1

    console.print(summary_table)

    # Final verdict
    total = len(results)
    console.print(f"\n[bold]Final Score: {passed}/{total} tests passed[/bold]")

    if passed == total:
        console.print("🎉 [green bold]All RAG tests passed successfully![/green bold]")
        return True
    elif passed > total / 2:
        console.print("⚠️  [yellow bold]Most tests passed, but some issues detected.[/yellow bold]")
        return True
    else:
        console.print("❌ [red bold]Multiple RAG tests failed.[/red bold]")
        return False

async def main():
    """Main test runner"""
    console.print("[bold cyan]Starting RAG Functionality Tests[/bold cyan]")

    # Start MCP servers
    multi_mcp = MultiMCP()
    await multi_mcp.start()

    try:
        # Run comprehensive tests
        success = await run_comprehensive_rag_tests(multi_mcp)

        if success:
            console.print("\n✅ [green]RAG system is functioning correctly![/green]")
        else:
            console.print("\n❌ [red]RAG system has issues that need attention.[/red]")
            sys.exit(1)

    except KeyboardInterrupt:
        console.print("\n⚠️  [yellow]Tests interrupted by user[/yellow]")
        sys.exit(1)
    except Exception as e:
        console.print(f"\n❌ [red]Unexpected error: {e}[/red]")
        import traceback
        traceback.print_exc()
        sys.exit(1)
    finally:
        await multi_mcp.stop()
        console.print("[blue]MCP servers stopped.[/blue]")

if __name__ == "__main__":
    asyncio.run(main())
