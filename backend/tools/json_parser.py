import json


def normalize_quotes(text):
    replacements = {
        "“": '"',
        "”": '"',
        "‘": "'",
        "’": "'",
    }
    for old, new in replacements.items():
        text = text.replace(old, new)
    return text


def strip_json_fence(text):
    lines = text.strip().splitlines()
    lines = [line for line in lines if not line.strip().startswith("```")]
    return "\n".join(lines)


def read_json_from_string(text: str) -> dict:
    cleaned = normalize_quotes(strip_json_fence(text))

    try:
        parsed = json.loads(cleaned)
        if isinstance(parsed, dict):
            top_keys = list(parsed.keys())
        elif isinstance(parsed, list) and len(parsed) > 0 and isinstance(parsed[0], dict):
            top_keys = list(parsed[0].keys())
        else:
            top_keys = []
        return {
            "valid_json": True,
            "top_keys": top_keys,
            "parsed": parsed,
        }
    except json.JSONDecodeError as exc:
        return {
            "valid_json": False,
            "error": str(exc),
        }

