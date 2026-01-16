# Using Google Gemini with RAG (Instead of Ollama)

## Overview

The RAG system can work with either:
1. **Ollama** (local models) - `server_rag.py`
2. **Google Gemini** (cloud API) - `server_rag_gemini.py`

## Why Use Gemini Instead of Ollama?

### Advantages of Gemini:
- ✅ **No local installation** - No need to install and run Ollama locally
- ✅ **Better embeddings** - Google's text-embedding-004 model (768 dimensions)
- ✅ **Faster processing** - Cloud-based, no local GPU required
- ✅ **Multimodal support** - Native image understanding with Gemini 1.5 Flash
- ✅ **Always available** - No need to keep Ollama server running
- ✅ **Free tier available** - Generous free quota for development

### Advantages of Ollama:
- ✅ **Complete privacy** - All data stays on your machine
- ✅ **No API costs** - Free to use after setup
- ✅ **Offline capability** - Works without internet
- ✅ **No rate limits** - Limited only by your hardware

## Setup Instructions

### 1. Get Your Gemini API Key

1. Visit [Google AI Studio](https://aistudio.google.com/app/apikey)
2. Click "Create API Key"
3. Copy your API key

### 2. Configure Environment Variable

Your `.env` file already has the structure. Just ensure your key is set:

```bash
GEMINI_API_KEY=your_actual_api_key_here
```

### 3. Install Required Package

```bash
# Using uv (recommended)
uv add google-generativeai

# Or using pip
pip install google-generativeai
```

### 4. Switch to Gemini RAG Server

Edit `mcp_servers/multi_mcp.py` and change line 26 from:

```python
"args": ["run", str(server_root / "server_rag.py")],
```

To:

```python
"args": ["run", str(server_root / "server_rag_gemini.py")],
```

That's it! The system will now use Google Gemini instead of Ollama.

## What Changed Under the Hood?

### Embedding Generation
**Ollama:**
```python
# Uses local nomic-embed-text model
POST http://localhost:11434/api/embeddings
```

**Gemini:**
```python
# Uses Google's text-embedding-004 model
genai.embed_content(
    model="models/text-embedding-004",
    content=text,
    task_type="retrieval_document"
)
```

### Text Generation (Semantic Analysis)
**Ollama:**
```python
# Uses local phi4 model
POST http://localhost:11434/api/chat
```

**Gemini:**
```python
# Uses Gemini 1.5 Flash
model = genai.GenerativeModel("gemini-1.5-flash")
response = model.generate_content(prompt)
```

### Image Captioning
**Ollama:**
```python
# Uses local gemma3:12b with base64 encoded images
POST http://localhost:11434/api/generate
```

**Gemini:**
```python
# Uses Gemini 1.5 Flash with native multimodal support
model = genai.GenerativeModel("gemini-1.5-flash")
response = model.generate_content([prompt, PIL_image])
```

## Testing Gemini RAG

After switching to Gemini, test it with:

```bash
# Create a test script specifically for Gemini
.venv/bin/python test_rag_gemini.py
```

Or use the existing test by ensuring the multi_mcp.py points to server_rag_gemini.py:

```bash
.venv/bin/python test_rag_functionality.py
```

## Storage Locations

The Gemini version uses a separate index directory to avoid conflicts:

- **Ollama Index**: `mcp_servers/faiss_index/`
- **Gemini Index**: `mcp_servers/faiss_index_gemini/`

This allows you to switch between them without re-indexing.

## Cost Considerations

### Google Gemini Free Tier (as of 2026):
- **Embeddings**: 1,500 requests/day (free)
- **Gemini 1.5 Flash**: 15 requests/minute, 1,500 requests/day (free)
- **Rate Limits**: Very generous for development/testing

For production use with high volume, you may need to upgrade to a paid plan.

### Ollama:
- Completely free (after hardware costs)
- Limited by your GPU/CPU capabilities

## Switching Back to Ollama

Simply revert the change in `multi_mcp.py`:

```python
"args": ["run", str(server_root / "server_rag.py")],
```

And ensure Ollama is running:

```bash
ollama serve
```

## Troubleshooting

### "GEMINI_API_KEY not found"
- Check your `.env` file has the key set
- Restart your Python process after updating .env

### "API quota exceeded"
- You've hit the free tier limit
- Wait for the quota to reset (daily)
- Or upgrade to a paid plan

### "Module 'google.generativeai' not found"
```bash
uv add google-generativeai
# or
pip install google-generativeai
```

### Embedding dimension mismatch
If you switch between Ollama (768d) and Gemini (768d), they should match. But if you get dimension errors:
- Delete the old index directory
- Let the system rebuild it with the new model

## Performance Comparison

Based on typical usage:

| Metric | Ollama | Gemini |
|--------|---------|---------|
| Embedding Speed | ~50ms | ~200ms |
| Text Generation | ~500ms | ~300ms |
| Image Captioning | ~2s | ~1s |
| Setup Complexity | High | Low |
| Internet Required | No | Yes |
| Cost | Free (local) | Free tier available |

## Recommendation

- **For Development/Testing**: Use Gemini (easier setup, no local resources)
- **For Production (Privacy)**: Use Ollama (data stays local)
- **For Production (Scale)**: Use Gemini (better performance, managed service)

## Next Steps

1. Test both versions with your documents
2. Compare embedding quality for your specific use case
3. Monitor API usage if using Gemini
4. Consider hybrid approach: Gemini for development, Ollama for production
