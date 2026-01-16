"""
Quick test to verify Google Gemini API is working correctly
Tests embedding generation and text generation
"""

import os
import sys
from dotenv import load_dotenv
import google.generativeai as genai

# Load environment variables
load_dotenv()

def test_gemini_setup():
    """Test Gemini API setup and basic functionality"""

    print("=" * 60)
    print("🔍 Testing Google Gemini Setup")
    print("=" * 60)

    # Check API key
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        print("❌ ERROR: GEMINI_API_KEY not found in .env file")
        print("   Please add your API key to .env:")
        print("   GEMINI_API_KEY=your_key_here")
        return False

    print(f"✅ API Key found: {api_key[:10]}...{api_key[-4:]}")

    try:
        # Configure Gemini
        genai.configure(api_key=api_key)
        print("✅ Gemini API configured")

        # Test 1: Embedding Generation
        print("\n" + "-" * 60)
        print("Test 1: Embedding Generation")
        print("-" * 60)

        test_text = "This is a test sentence for embedding generation."
        result = genai.embed_content(
            model="models/text-embedding-004",
            content=test_text,
            task_type="retrieval_document"
        )

        embedding = result['embedding']
        print(f"✅ Embedding generated successfully")
        print(f"   Dimension: {len(embedding)}")
        print(f"   Sample values: {embedding[:3]}")

        # Test 2: Text Generation
        print("\n" + "-" * 60)
        print("Test 2: Text Generation")
        print("-" * 60)

        model = genai.GenerativeModel("gemini-2.5-flash")
        response = model.generate_content("Say 'Hello, Gemini is working!' and nothing else.")

        print(f"✅ Text generated successfully")
        print(f"   Response: {response.text}")

        # Test 3: Semantic Analysis (RAG use case)
        print("\n" + "-" * 60)
        print("Test 3: Semantic Analysis for RAG")
        print("-" * 60)

        chunk1 = "Cricket is a bat-and-ball game played between two teams."
        chunk2 = "The weather forecast predicts rain tomorrow."

        prompt = f"""Are these two text chunks related to the same topic?

Chunk 1: "{chunk1}"
Chunk 2: "{chunk2}"

Answer with just 'Yes' or 'No'."""

        response = model.generate_content(prompt)
        print(f"✅ Semantic analysis completed")
        print(f"   Question: Are the chunks related?")
        print(f"   Answer: {response.text.strip()}")

        # Summary
        print("\n" + "=" * 60)
        print("🎉 All tests passed! Gemini is ready for RAG.")
        print("=" * 60)
        print("\nNext steps:")
        print("1. Update multi_mcp.py to use server_rag_gemini.py")
        print("2. Run: .venv/bin/python test_rag_functionality.py")
        print("3. Or check RAG_GEMINI_SETUP.md for detailed instructions")

        return True

    except Exception as e:
        print(f"\n❌ ERROR: {e}")
        print("\nTroubleshooting:")
        print("1. Check your API key is valid")
        print("2. Ensure you have internet connection")
        print("3. Check if you've exceeded API quota")
        print("4. Visit: https://aistudio.google.com/app/apikey")
        return False

if __name__ == "__main__":
    success = test_gemini_setup()
    sys.exit(0 if success else 1)
