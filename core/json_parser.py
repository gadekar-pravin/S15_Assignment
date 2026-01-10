import json
import re
from json_repair import repair_json

class JsonParsingError(Exception):
    """
    Custom exception raised when JSON parsing fails after all attempts.
    """
    pass

def extract_json_block_fenced(text: str) -> str | None:
    """
    Extracts the content of a ```json fenced code block from the given text.

    Args:
        text (str): The input text containing the fenced code block.

    Returns:
        str | None: The content of the JSON block if found, otherwise None.
    """
    match = re.search(r"(?i)```json\s*(\{.*?\})\s*```", text, re.DOTALL)
    return match.group(1) if match else None

def extract_json_block_balanced(text: str) -> str | None:
    """
    Finds the largest balanced JSON-looking block from the first '{' to the last '}'.

    Args:
        text (str): The input text to search for a JSON block.

    Returns:
        str | None: The extracted JSON string if found, otherwise None.
    """
    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end > start:
        return text[start:end+1]
    return None

def validate_required_keys(obj: dict, required_keys: list[str]):
    """
    Ensures all required keys exist in the parsed dictionary.

    Args:
        obj (dict): The dictionary to validate.
        required_keys (list[str]): A list of keys that must be present in the dictionary.

    Raises:
        JsonParsingError: If any of the required keys are missing.
    """
    for key in required_keys:
        if key not in obj:
            raise JsonParsingError(f"Missing required key: {key}")

def _parse_and_validate(raw_json: str, required_keys: list[str] = None) -> dict:
    """
    Helper to parse a JSON string and optionally validate it against a required schema.

    Args:
        raw_json (str): The JSON string to parse.
        required_keys (list[str], optional): A list of keys that must be present in the parsed dictionary. Defaults to None.

    Returns:
        dict: The parsed JSON object.

    Raises:
        json.JSONDecodeError: If parsing fails.
        JsonParsingError: If validation fails.
    """
    parsed = json.loads(raw_json)
    if required_keys:
        validate_required_keys(parsed, required_keys)
    return parsed

def parse_llm_json(text: str, required_keys: list[str] = None, debug: bool = False) -> dict:
    """
    Attempts to robustly parse a JSON object from LLM output.

    It tries the following strategies in order:
      1. Extracting from a fenced JSON block (```json ... ```).
      2. Extracting from the largest balanced brace block ({ ... }).
      3. Using the `json_repair` library to repair malformed JSON.

    Args:
        text (str): The raw text output from the LLM.
        required_keys (list[str], optional): A list of keys that must be present in the parsed JSON. Defaults to None.
        debug (bool, optional): If True, prints debug information during parsing. Defaults to False.

    Returns:
        dict: The parsed and validated JSON object.

    Raises:
        JsonParsingError: If all parsing attempts fail or validation fails.
    """
    extractors = [
        ("fenced", extract_json_block_fenced),
        ("balanced", extract_json_block_balanced)
    ]

    for name, extractor in extractors:
        raw_json = extractor(text)
        if raw_json:
            try:
                if debug: print(f"[DEBUG] Attempting {name} extraction...")
                return _parse_and_validate(raw_json, required_keys)
            except json.JSONDecodeError:
                if debug: print(f"[DEBUG] JSON decode failed for {name}.")
                continue
            except JsonParsingError:
                raise  # Required key missing

    # Final attempt: repair
    raw_json = extract_json_block_balanced(text)
    if raw_json:
        try:
            if debug: print(f"[DEBUG] Attempting auto-repair...")
            repaired = repair_json(raw_json)
            return _parse_and_validate(repaired, required_keys)
        except Exception:
            if debug: print(f"[DEBUG] Repair attempt failed.")

    raise JsonParsingError("All attempts to parse JSON from LLM output failed.")
