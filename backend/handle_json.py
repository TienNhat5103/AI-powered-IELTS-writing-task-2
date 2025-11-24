import json

# Hàm thay ngoặc cong thành ngoặc thẳng
def normalize_quotes(text):
    replacements = {
        '“': '"', '”': '"',
        '‘': "'", '’': "'"
    }
    for old, new in replacements.items():
        text = text.replace(old, new)
    return text

# Hàm loại bỏ ```json ... ```
def strip_json_fence(text):
    lines = text.strip().splitlines()
    lines = [line for line in lines if not line.strip().startswith("```")]
    return "\n".join(lines)

def read_json_from_string(text: str) -> dict:
    """
    Nhận vào một chuỗi có chứa JSON (có thể có fence ```json``` hoặc ngoặc cong),
    rồi làm sạch và parse thành dict.
    Trả về:
      - valid_json: True/False
      - top_keys: danh sách key ở cấp cao nhất (nếu valid_json)
      - parsed: object đã parse (nếu valid_json)
      - error: lỗi decode (nếu invalid)
    """
    # Làm sạch dấu ngoặc “ ” trở thành " và loại bỏ fence ``` 
    cleaned = normalize_quotes(strip_json_fence(text))
    try:
        parsed = json.loads(cleaned)
        return {
            "valid_json": True,
            "top_keys": list(parsed.keys()),
            "parsed": parsed
        }
    except json.JSONDecodeError as e:
        return {
            "valid_json": False,
            "error": str(e)
        }