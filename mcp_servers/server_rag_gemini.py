"""
RAG Server using Google Gemini AI instead of Ollama
This version uses:
- text-embedding-004 for embeddings
- gemini-1.5-flash for text generation (semantic analysis)
- gemini-1.5-flash for image captioning (multimodal)
"""

from mcp.server.fastmcp import FastMCP, Image
from mcp.server.fastmcp.prompts import base
from mcp.types import TextContent
from mcp import types
from PIL import Image as PILImage
import math
import sys
import os
import json
import faiss
import numpy as np
from pathlib import Path
from markitdown import MarkItDown
import time
from models import SearchDocumentsInput, MarkdownOutput, FilePathInput, UrlInput
from tqdm import tqdm
import hashlib
from pydantic import BaseModel
import sqlite3
import trafilatura
import pymupdf4llm
import re
import base64
import asyncio
import google.generativeai as genai
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

mcp = FastMCP("Local Storage RAG (Gemini)")

# Configure Google Gemini
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
if not GEMINI_API_KEY:
    raise ValueError("GEMINI_API_KEY not found in environment variables")

genai.configure(api_key=GEMINI_API_KEY)

# Gemini Models
EMBED_MODEL = "models/text-embedding-004"
TEXT_MODEL = "gemini-2.5-flash"  # For semantic analysis
VISION_MODEL = "gemini-2.5-flash"  # For image captioning (supports multimodal)

CHUNK_SIZE = 256
CHUNK_OVERLAP = 40
MAX_CHUNK_LENGTH = 512
TOP_K = 3
ROOT = Path(__file__).parent.resolve()


def get_embedding(text: str) -> np.ndarray:
    """
    Computes the embedding for a given text using Google's Gemini API.

    Args:
        text (str): The input text.

    Returns:
        np.ndarray: The embedding vector as a float32 numpy array.
    """
    try:
        result = genai.embed_content(
            model=EMBED_MODEL,
            content=text,
            task_type="retrieval_document"
        )
        return np.array(result['embedding'], dtype=np.float32)
    except Exception as e:
        mcp_log("ERROR", f"Embedding generation failed: {e}")
        raise


def chunk_text(text, size=CHUNK_SIZE, overlap=CHUNK_OVERLAP):
    """
    Generates overlapping chunks of text.

    Args:
        text (str): The text to chunk.
        size (int, optional): The number of words per chunk. Defaults to CHUNK_SIZE.
        overlap (int, optional): The number of overlapping words. Defaults to CHUNK_OVERLAP.

    Yields:
        str: A text chunk.
    """
    words = text.split()
    for i in range(0, len(words), size - overlap):
        yield " ".join(words[i:i+size])


def mcp_log(level: str, message: str) -> None:
    """
    Logs messages to stderr for MCP protocol compatibility.

    Args:
        level (str): The log level (e.g., "INFO", "ERROR").
        message (str): The message content.
    """
    if level in ["ERROR", "WARN"]:
        sys.stderr.write(f"{level}: {message}\n")
        sys.stderr.flush()


def are_related(chunk1: str, chunk2: str, index: int) -> bool:
    """
    Uses Gemini to determine if two text chunks are semantically related.

    Args:
        chunk1 (str): The first text chunk.
        chunk2 (str): The second text chunk.
        index (int): The index of the first chunk (for logging).

    Returns:
        bool: True if related, False otherwise.
    """
    prompt = f"""
You are helping to segment a document into topic-based chunks. Unfortunately, the sentences are mixed up.

CHUNK 1: "{chunk1}"
CHUNK 2: "{chunk2}"

Should these two chunks appear in the **same paragraph or flow of writing**?

Even if the subject changes slightly (e.g., One person to another), treat them as related **if they belong to the same broader context or topic** (like cricket, AI, or real estate).

Also consider cues like continuity words (e.g., "However", "But", "Also") or references that link the sentences.

Answer with:
Yes – if the chunks should appear together in the same paragraph or section
No – if they are about different topics and should be separated

Just respond in one word (Yes or No), and do not provide any further explanation.
"""
    print(f"\nComparing chunk {index} and {index+1}")
    print(f"  Chunk {index} → {chunk1[:60]}{'...' if len(chunk1) > 60 else ''}")
    print(f"  Chunk {index+1} → {chunk2[:60]}{'...' if len(chunk2) > 60 else ''}")

    try:
        model = genai.GenerativeModel(TEXT_MODEL)
        response = model.generate_content(
            prompt,
            safety_settings={
                'HARASSMENT': 'BLOCK_NONE',
                'HATE_SPEECH': 'BLOCK_NONE',
                'SEXUALLY_EXPLICIT': 'BLOCK_NONE',
                'DANGEROUS_CONTENT': 'BLOCK_NONE'
            }
        )

        # Handle blocked responses - default to not related
        if not response.parts:
            print(f"Model response blocked by safety, treating as not related")
            return False

        reply = response.text.strip().lower()
        print(f"Model reply: {reply}")
        return reply.startswith("yes")
    except Exception as e:
        mcp_log("ERROR", f"Gemini API error in are_related: {e}")
        return False


@mcp.tool()
def search_stored_documents_rag(input: SearchDocumentsInput) -> list[str]:
    """
    Searches stored documents (PDF, DOCX, TXT) for relevant extracts using RAG.

    Args:
        input (SearchDocumentsInput): The search parameters containing the query.

    Returns:
        list[str]: A list of relevant document extracts with source metadata.
    """
    ensure_faiss_ready()
    query = input.query
    mcp_log("SEARCH", f"Query: {query}")
    try:
        index = faiss.read_index(str(ROOT / "faiss_index" / "index.bin"))
        metadata = json.loads((ROOT / "faiss_index" / "metadata.json").read_text())

        # Use Gemini for query embedding
        query_vec = get_embedding(query).reshape(1, -1)
        D, I = index.search(query_vec, k=5)
        results = []
        for idx in I[0]:
            data = metadata[idx]
            results.append(f"{data['chunk']}\n[Source: {data['doc']}, ID: {data['chunk_id']}]")
        return results
    except Exception as e:
        return [f"ERROR: Failed to search: {str(e)}"]


def caption_image(img_url_or_path: str) -> str:
    """
    Generates a caption for an image using Gemini's vision capabilities.

    Args:
        img_url_or_path (str): The file path or URL of the image.

    Returns:
        str: The generated caption or error message.
    """
    mcp_log("CAPTION", f"Attempting to caption image: {img_url_or_path}")

    try:
        # Load the image
        if img_url_or_path.startswith("http://") or img_url_or_path.startswith("https://"):
            import requests
            response = requests.get(img_url_or_path)
            if response.status_code != 200:
                raise Exception(f"HTTP {response.status_code}")
            from io import BytesIO
            img = PILImage.open(BytesIO(response.content))
        else:
            full_path = Path(__file__).parent / "documents" / img_url_or_path
            full_path = full_path.resolve()
            if not full_path.exists():
                mcp_log("ERROR", f"Image file not found: {full_path}")
                return f"[Image file not found: {img_url_or_path}]"
            img = PILImage.open(full_path)

        # Use Gemini Vision to caption the image
        model = genai.GenerativeModel(VISION_MODEL)
        prompt = "Look only at the attached image. If it's code, output it exactly as text. If it's a visual scene, describe it as you would for an image alt-text. Never generate new code. Return only the contents of the image."

        response = model.generate_content(
            [prompt, img],
            safety_settings={
                'HARASSMENT': 'BLOCK_NONE',
                'HATE_SPEECH': 'BLOCK_NONE',
                'SEXUALLY_EXPLICIT': 'BLOCK_NONE',
                'DANGEROUS_CONTENT': 'BLOCK_NONE'
            }
        )

        # Handle blocked responses
        if not response.parts:
            mcp_log("WARN", f"Gemini blocked image caption response, using placeholder")
            return "[Image content blocked by safety filters]"

        caption = response.text.strip()

        mcp_log("CAPTION", f"Caption generated: {caption}")
        return caption if caption else "[No caption returned]"

    except Exception as e:
        mcp_log("ERROR", f"Failed to caption image {img_url_or_path}: {e}")
        return f"[Image could not be processed: {img_url_or_path}]"


def replace_images_with_captions(markdown: str) -> str:
    """
    Parses markdown content, finds images, generates captions for them, and replaces the image markup with the caption.

    Args:
        markdown (str): The markdown text.

    Returns:
        str: The markdown text with images replaced by captions.
    """
    def replace(match):
        alt, src = match.group(1), match.group(2)
        try:
            caption = caption_image(src)
            # Attempt to delete only if local and file exists
            if not src.startswith("http"):
                img_path = Path(__file__).parent / "documents" / src
                if img_path.exists():
                    img_path.unlink()
                    mcp_log("INFO", f"Deleted image after captioning: {img_path}")
            return f"**Image:** {caption}"
        except Exception as e:
            mcp_log("WARN", f"Image deletion failed: {e}")
            return f"[Image could not be processed: {src}]"

    return re.sub(r'!\[(.*?)\]\((.*?)\)', replace, markdown)


@mcp.tool()
def convert_pdf_to_markdown(string: str) -> MarkdownOutput:
    """
    Converts a PDF file to Markdown format, handling images by extracting and captioning them.

    Args:
        string (str): Path to the PDF file.

    Returns:
        MarkdownOutput: The resulting markdown content.
    """
    if not os.path.exists(string):
        return MarkdownOutput(markdown=f"File not found: {string}")

    ROOT = Path(__file__).parent.resolve()
    global_image_dir = ROOT / "documents" / "images"
    global_image_dir.mkdir(parents=True, exist_ok=True)

    # Actual markdown with relative image paths
    markdown = pymupdf4llm.to_markdown(
        string,
        write_images=True,
        image_path=str(global_image_dir)
    )

    # Re-point image links in the markdown
    markdown = re.sub(
        r'!\[\]\((.*?/images/)([^)]+)\)',
        r'![](images/\2)',
        markdown.replace("\\", "/")
    )

    markdown = replace_images_with_captions(markdown)
    return MarkdownOutput(markdown=markdown)


@mcp.tool()
def caption_images(img_url_or_path: str) -> str:
    """
    Tool exposed to caption an image.

    Args:
        img_url_or_path (str): URL or path to the image.

    Returns:
        str: The image description.
    """
    caption = caption_image(img_url_or_path)
    return "The contents of this image are: " + caption


def semantic_merge(text: str) -> list[str]:
    """
    Splits text semantically using Gemini. It detects if a chunk contains multiple distinct topics
    and splits them intelligently, carrying over the second topic to the next chunk.

    Args:
        text (str): The input text.

    Returns:
        list[str]: A list of semantically coherent text chunks.
    """
    WORD_LIMIT = 512
    words = text.split()
    i = 0
    final_chunks = []

    while i < len(words):
        # 1. Take next chunk of words (and prepend leftovers if any)
        chunk_words = words[i:i + WORD_LIMIT]
        chunk_text = " ".join(chunk_words).strip()

        prompt = f"""
You are a markdown document segmenter.

Here is a portion of a markdown document:

---
{chunk_text}
---

If this chunk clearly contains **more than one distinct topic or section**, reply ONLY with the **second part**, starting from the first sentence or heading of the new topic.

If it's only one topic, reply with NOTHING.

Keep markdown formatting intact.
"""

        try:
            model = genai.GenerativeModel(TEXT_MODEL)
            response = model.generate_content(
                prompt,
                safety_settings={
                    'HARASSMENT': 'BLOCK_NONE',
                    'HATE_SPEECH': 'BLOCK_NONE',
                    'SEXUALLY_EXPLICIT': 'BLOCK_NONE',
                    'DANGEROUS_CONTENT': 'BLOCK_NONE'
                }
            )

            # Handle blocked responses gracefully
            if not response.parts:
                mcp_log("WARN", f"Gemini blocked response for semantic chunking, treating as single chunk")
                final_chunks.append(chunk_text)
                i += WORD_LIMIT
                continue

            reply = response.text.strip()

            if reply:
                # If LLM returned second part, separate it
                split_point = chunk_text.find(reply)
                if split_point != -1:
                    first_part = chunk_text[:split_point].strip()
                    second_part = reply.strip()

                    final_chunks.append(first_part)

                    # Get remaining words from second_part and re-use them in next batch
                    leftover_words = second_part.split()
                    words = leftover_words + words[i + WORD_LIMIT:]
                    i = 0  # restart loop with leftover + remaining
                    continue
                else:
                    # fallback: if split point not found
                    final_chunks.append(chunk_text)
            else:
                final_chunks.append(chunk_text)

        except Exception as e:
            mcp_log("ERROR", f"Semantic chunking Gemini error: {e}")
            final_chunks.append(chunk_text)

        i += WORD_LIMIT

    return final_chunks


def process_documents():
    """
    Processes all documents in the 'documents' directory.
    Converts them to markdown, chunks them, computes embeddings using Gemini, and builds/updates the FAISS index.
    Supports PDF, HTML, and other formats supported by MarkItDown.
    """
    mcp_log("INFO", "Indexing documents with Gemini-based RAG pipeline...")
    ROOT = Path(__file__).parent.resolve()
    DOC_PATH = ROOT / "documents"
    INDEX_CACHE = ROOT / "faiss_index_gemini"
    INDEX_CACHE.mkdir(exist_ok=True)
    INDEX_FILE = INDEX_CACHE / "index.bin"
    METADATA_FILE = INDEX_CACHE / "metadata.json"
    CACHE_FILE = INDEX_CACHE / "doc_index_cache.json"

    def file_hash(path):
        return hashlib.md5(Path(path).read_bytes()).hexdigest()

    CACHE_META = json.loads(CACHE_FILE.read_text()) if CACHE_FILE.exists() else {}
    metadata = json.loads(METADATA_FILE.read_text()) if METADATA_FILE.exists() else []
    index = faiss.read_index(str(INDEX_FILE)) if INDEX_FILE.exists() else None

    for file in DOC_PATH.glob("*.*"):
        if file.name.startswith('.'):  # Skip hidden files
            continue

        fhash = file_hash(file)
        if file.name in CACHE_META and CACHE_META[file.name] == fhash:
            mcp_log("SKIP", f"Skipping unchanged file: {file.name}")
            continue

        mcp_log("PROC", f"Processing: {file.name}")
        try:
            ext = file.suffix.lower()
            markdown = ""

            if ext == ".pdf":
                mcp_log("INFO", f"Using MuPDF4LLM to extract {file.name}")
                markdown = convert_pdf_to_markdown(str(file)).markdown

            elif ext in [".html", ".htm"]:
                mcp_log("INFO", f"Using Trafilatura to extract {file.name}")
                content = trafilatura.extract(file.read_text())
                markdown = content if content else ""

            else:
                # Fallback to MarkItDown for other formats
                converter = MarkItDown()
                mcp_log("INFO", f"Using MarkItDown fallback for {file.name}")
                markdown = converter.convert(str(file)).text_content

            if not markdown.strip():
                mcp_log("WARN", f"No content extracted from {file.name}")
                continue

            if len(markdown.split()) < 10:
                mcp_log("WARN", f"Content too short for semantic merge in {file.name} → Skipping chunking.")
                chunks = [markdown.strip()]
            else:
                mcp_log("INFO", f"Running semantic merge on {file.name} with {len(markdown.split())} words")
                chunks = semantic_merge(markdown)

            embeddings_for_file = []
            new_metadata = []
            for i, chunk in enumerate(tqdm(chunks, desc=f"Embedding {file.name} (Gemini)")):
                embedding = get_embedding(chunk)
                embeddings_for_file.append(embedding)
                new_metadata.append({
                    "doc": file.name,
                    "chunk": chunk,
                    "chunk_id": f"{file.stem}_{i}"
                })

            if embeddings_for_file:
                if index is None:
                    dim = len(embeddings_for_file[0])
                    index = faiss.IndexFlatL2(dim)
                index.add(np.stack(embeddings_for_file))
                metadata.extend(new_metadata)
                CACHE_META[file.name] = fhash

                # Save index and metadata
                CACHE_FILE.write_text(json.dumps(CACHE_META, indent=2))
                METADATA_FILE.write_text(json.dumps(metadata, indent=2))
                faiss.write_index(index, str(INDEX_FILE))
                mcp_log("SAVE", f"Saved FAISS index and metadata after processing {file.name}")

        except Exception as e:
            mcp_log("ERROR", f"Failed to process {file.name}: {e}")
            import traceback
            traceback.print_exc()
    mcp_log("INFO", "READY")


def ensure_faiss_ready():
    """
    Ensures that the FAISS index is up-to-date by checking for new or modified documents.
    This function is called before every RAG search to keep the index current.

    The process_documents() function is smart:
    - Skips unchanged files (using MD5 hash check)
    - Only indexes new or modified documents
    - Fast when no changes detected
    """
    # Always run process_documents - it will skip unchanged files automatically
    mcp_log("INFO", "Checking for new or modified documents...")
    process_documents()


async def main():
    mcp_log("INFO", "STARTING THE GEMINI-BASED RAG SERVER")

    if len(sys.argv) > 1 and sys.argv[1] == "dev":
        mcp.run()  # Run without transport for dev server
    else:
        # Start the server in a separate thread
        import threading
        server_thread = threading.Thread(target=lambda: mcp.run(transport="stdio"))
        server_thread.daemon = True
        server_thread.start()

        # Wait a moment for the server to start
        await asyncio.sleep(2)

        # Keep the main thread alive
        try:
            while True:
                await asyncio.sleep(1)
        except KeyboardInterrupt:
            mcp_log("INFO", "\nShutting down...")

if __name__ == "__main__":
    asyncio.run(main())
