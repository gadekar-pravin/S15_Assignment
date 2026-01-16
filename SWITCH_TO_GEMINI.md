# Quick Guide: Switch RAG from Ollama to Google Gemini

## ✅ Setup Complete!

Your Gemini API is already configured and working! Here's how to switch your RAG system from Ollama to Gemini.

## 1-Minute Switch Guide

### Step 1: Edit `mcp_servers/multi_mcp.py`

Find line 26 and change:

```python
# FROM (Ollama):
"args": ["run", str(server_root / "server_rag.py")],

# TO (Gemini):
"args": ["run", str(server_root / "server_rag_gemini.py")],
```

### Step 2: That's it!

Run your application normally:

```bash
.venv/bin/python app.py
```

Or test the RAG system:

```bash
.venv/bin/python test_rag_functionality.py
```

## What You Get with Gemini

✅ **Working Now:**
- Embeddings: `text-embedding-004` (768 dimensions)
- Text Analysis: `gemini-2.5-flash` (Latest model!)
- Image Captioning: `gemini-2.5-flash` (Multimodal)
- No Ollama server required
- Faster initial setup

## Key Differences

| Feature | Ollama | Gemini |
|---------|--------|---------|
| Setup | Install Ollama + models | Just API key |
| Speed | Depends on hardware | Cloud-optimized |
| Privacy | 100% local | Cloud-based |
| Cost | Free (hardware) | Free tier available |
| Internet | Not required | Required |
| Models | nomic-embed-text, phi4, gemma3 | gemini-2.5-flash, text-embedding-004 |

## Test Your Setup

Verify Gemini is working:

```bash
.venv/bin/python test_gemini_setup.py
```

Expected output:
```
✅ API Key found
✅ Gemini API configured
✅ Embedding generated successfully
✅ Text generated successfully
✅ Semantic analysis completed
🎉 All tests passed!
```

## File Locations

After switching, your files will be organized as:

```
mcp_servers/
├── server_rag.py           # Ollama version
├── server_rag_gemini.py    # Gemini version ← NEW
├── faiss_index/            # Ollama embeddings
└── faiss_index_gemini/     # Gemini embeddings ← NEW
```

The system automatically creates separate indexes so you can switch back and forth without conflicts.

## Switch Back to Ollama

Just revert the change in `multi_mcp.py`:

```python
"args": ["run", str(server_root / "server_rag.py")],
```

And make sure Ollama is running:
```bash
ollama serve
```

## API Usage & Limits

Your Gemini API (Free Tier) includes:

- **Embeddings**: 1,500 requests/day
- **Text Generation**: 15 requests/minute, 1,500/day
- **Rate Limits**: Generous for development

For details, visit: https://ai.google.dev/pricing

## Troubleshooting

### "Module 'google.generativeai' not found"
Already installed! But if needed:
```bash
uv add google-generativeai
```

### Package deprecation warning
The warning is informational. The package still works perfectly. Google recommends migrating to `google.genai` in the future, but `google.generativeai` continues to function.

### API Errors
1. Check your API key in `.env`
2. Verify internet connection
3. Check free tier limits: https://aistudio.google.com/app/apikey

## Performance Tips

For best results with Gemini:

1. **Batch Processing**: Process documents in smaller batches if you hit rate limits
2. **Caching**: The system automatically caches embeddings
3. **Model Selection**: gemini-2.5-flash is optimized for speed and cost

## Current Models Used

- **Embeddings**: `text-embedding-004` (Google's latest)
- **Text**: `gemini-2.5-flash` (Newest Gemini model)
- **Vision**: `gemini-2.5-flash` (Multimodal capable)

## Questions?

- See full documentation: `RAG_GEMINI_SETUP.md`
- Test Gemini: `test_gemini_setup.py`
- Test RAG: `test_rag_functionality.py`

---

**Ready to switch?** Just edit one line in `multi_mcp.py` and you're done! 🚀
