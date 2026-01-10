import json
import time
from pathlib import Path

# Config
INPUT_JSON_PATH = "metadata.json"
OUTPUT_JSON_PATH = "triplet_output.json"
MODEL_NAME = "qwen2.5:32b-instruct-q4_0"
PROMPT_HEADER = """Extract all factual triplets from the following text in the format: (subject, relation, object).

Each triplet must represent a factual relationship between two entities or concepts, clearly grounded in the text. Use the format:

(subject, relation_subtype, object)

✅ RULES FOR RELATION FORMAT:
- The relation MUST be a two-word phrase using the format: relation_subtype (e.g., 'scores_run', 'represents_symbol', 'uses_technology')
- Do NOT use generic or vague verbs like 'is', 'has', 'does', 'are', etc.
- Do NOT use long phrases or full clauses as relation names.
- The two words must meaningfully describe the action or relationship — avoid filler verbs.
- Example good relations: 'represents_symbol', 'scores_run', 'uses_tool', 'develops_product'
- Example bad relations: 'is_a', 'does_work', 'has_property', 'is_part_of'

✅ RULES FOR TRIPLET COMPLETENESS:
- Do NOT return incomplete triplets.
- No field in the triplet (subject, relation, or object) can be empty or vague.
- You MUST infer missing elements using context from nearby sentences. Look both forward and backward in the text to resolve ambiguities or implied references.
- If necessary, rephrase or complete implied relations using concrete nouns or phrases available in the context.

✅ OTHER GUIDELINES:
- Focus only on factual or narrative text. Ignore metadata, code, log statements, or markup.
- Avoid repeating the same triplet unless clearly stated multiple times with new context.
- Do not add explanations or notes — just return the raw triplet list, one per line.

Your output should be a clean list of factual triplets, one per line, formatted exactly as:
(subject, relation_subtype, object)
"""



# Simulated model call
def call_ollama(model_name, prompt):
    """
    Calls the Ollama CLI to generate text based on a prompt.

    Args:
        model_name (str): The name of the model to use.
        prompt (str): The input prompt.

    Returns:
        str: The generated text.
    """
    # Replace with your actual call logic
    import subprocess
    result = subprocess.run(
        ["ollama", "run", model_name],
        input=prompt.encode("utf-8"),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    return result.stdout.decode("utf-8")

# Text chunking
def chunk_text(text, word_limit=200):
    """
    Splits text into chunks of a specified word limit.

    Args:
        text (str): The input text.
        word_limit (int, optional): The maximum words per chunk. Defaults to 200.

    Returns:
        list[str]: A list of text chunks.
    """
    words = text.split()
    return [" ".join(words[i:i + word_limit]) for i in range(0, len(words), word_limit)]

# Load JSON
if __name__ == "__main__":
    if not Path(INPUT_JSON_PATH).exists():
        print(f"Skipping triplet extraction: {INPUT_JSON_PATH} not found.")
        exit(0)

    with open(INPUT_JSON_PATH, "r", encoding="utf-8") as f:
        data = json.load(f)

    # Support your metadata.json format: list of dicts with 'chunk' fields
    if isinstance(data, list) and "chunk" in data[0]:
        full_text = " ".join(item["chunk"] for item in data)
    else:
        raise ValueError("Unsupported JSON structure — must contain 'chunk' fields in a list of objects.")


    # Prepare output file
    Path(OUTPUT_JSON_PATH).write_text("[]", encoding="utf-8")  # start with empty list

    # Process in 200-word chunks
    results = []
    for i, segment in enumerate(chunk_text(full_text, word_limit=200)):
        print(f"\n🔹 [Segment {i}] First 200 words:\n")
        print(segment[:500] + "...\n")

        prompt = f"{PROMPT_HEADER}\n\n{segment}"
        try:
            output = call_ollama(MODEL_NAME, prompt).strip()
            triplet_record = {
                "segment_index": i,
                "text": segment,
                "triplets": output
            }

            # Load current output
            with open(OUTPUT_JSON_PATH, "r", encoding="utf-8") as f:
                current_data = json.load(f)

            current_data.append(triplet_record)

            # Save back to file so you can see it grow
            with open(OUTPUT_JSON_PATH, "w", encoding="utf-8") as f:
                json.dump(current_data, f, indent=2)

            print(f"✅ Triplets saved for segment {i}")

        except Exception as e:
            print(f"❌ Error in segment {i}: {e}")
            continue

        time.sleep(1)  # Optional: throttle requests
