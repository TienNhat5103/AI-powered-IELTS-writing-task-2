import difflib
import re
import torch
from transformers import AutoTokenizer, T5ForConditionalGeneration
# initialize the model and tokenizer
tokenizer = None
model = None
tokenizer = None
model = None
device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
tokenizer = AutoTokenizer.from_pretrained("grammarly/coedit-large")
model = T5ForConditionalGeneration.from_pretrained("grammarly/coedit-large").to(device)
print(f"COEDIT Model and tokenizer loaded. Running on device: {device}")
    
def fix_grammar(text: str, tokenizer, model, device) -> str:
    prompt = "Fix grammar: " + text
    inputs = tokenizer(prompt, return_tensors="pt", truncation=True).to(device)
    outputs = model.generate(inputs.input_ids, max_length=64)
    output_text = tokenizer.decode(outputs[0], skip_special_tokens=True)
    return output_text

def split_text_into_chunks(text: str, tokenizer, max_tokens: int = 64) -> list:
    """
    Tách text thành các chunk nhỏ dựa theo câu, sao cho mỗi chunk không vượt quá max_tokens.
    Sử dụng regex để tách câu dựa trên dấu kết thúc câu (., !, ?).
    """
    # Tách theo các dấu kết thúc câu (bao gồm cả khoảng trắng phía sau)
    sentences = re.split(r'(?<=[.!?])\s+', text)
    chunks = []
    current_chunk = ""
    for sentence in sentences:
        test_chunk = current_chunk + (" " if current_chunk else "") + sentence
        tokens = tokenizer.tokenize(test_chunk)
        if len(tokens) <= max_tokens:
            current_chunk = test_chunk
        else:
            if current_chunk:
                chunks.append(current_chunk)
            current_chunk = sentence
    if current_chunk:
        chunks.append(current_chunk)
    return chunks

def annotate_differences(original_text: str, corrected_text: str) -> str:
    original_words = original_text.split()
    corrected_words = corrected_text.split()

    seq_matcher = difflib.SequenceMatcher(None, original_words, corrected_words)
    opcodes = seq_matcher.get_opcodes()

    def get_word_positions(text: str):
        positions = []
        for match in re.finditer(r'\S+', text):
            start, end = match.span()
            positions.append((match.group(), start, end))
        return positions

    original_positions = get_word_positions(original_text)
    annotated_text = ""
    last_index = 0

    for tag, i1, i2, j1, j2 in opcodes:
        if tag == "equal":
            if i1 < len(original_positions):
                segment_start = original_positions[i1][1]
                segment_end = original_positions[i2 - 1][2] if (i2 - 1) < len(original_positions) else len(original_text)
                annotated_text += original_text[last_index:segment_start]
                annotated_text += original_text[segment_start:segment_end]
                last_index = segment_end
        elif tag in ["replace", "delete"]:
            if i1 < len(original_positions):
                segment_start = original_positions[i1][1]
                segment_end = original_positions[i2 - 1][2] if (i2 - 1) < len(original_positions) else len(original_text)
                error_segment = original_text[segment_start:segment_end]
                suggestion = " ".join(corrected_words[j1:j2])
                annotated_text += original_text[last_index:segment_start]
                annotated_text += (
                    f"<span class='error-block' onclick='showSuggestion(this)' data-suggestion='{suggestion}'>{error_segment}</span>"
                )
                last_index = segment_end
        elif tag == "insert":
            suggestion = " ".join(corrected_words[j1:j2])
            annotated_text += f"<span class='suggestion'>{suggestion}</span>"

    annotated_text += original_text[last_index:]
    return annotated_text


def process_document(document_text: str, tokenizer, model, device, max_tokens: int = 64) -> str:    
    """
    Xử lý một tài liệu:
      - Tách tài liệu thành các đoạn dựa trên các ký tự xuống dòng liên tiếp,
        bằng cách sử dụng biểu thức chính quy có nhóm bắt để giữ lại các ký tự xuống dòng gốc.
      - Với mỗi đoạn (những đoạn không phải là chỉ chứa ký tự xuống dòng),
        nếu số token vượt quá max_tokens thì tách thành các chunk nhỏ và xử lý từng phần,
        còn lại thì xử lý trực tiếp.
      - Ghép lại kết quả đã annotate mà vẫn giữ nguyên định dạng ban đầu của người dùng (bao gồm tab, khoảng trắng, newlines).
    """
    # Dùng capturing group để tách các đoạn và giữ lại delimiter (các dòng xuống liên tiếp, có thể có khoảng trắng và tab)
    segments = re.split(r'(\n\s*\n)', document_text)
    annotated_segments = []
    
    for segment in segments:
        # Nếu segment chỉ chứa các ký tự xuống dòng (và khoảng trắng) thì giữ nguyên
        if re.fullmatch(r'\n\s*\n', segment):
            annotated_segments.append(segment)
        else:
            # Giữ nguyên cấu trúc ban đầu (không .strip() để bảo toàn tab, khoảng trắng ở đầu/đuôi)
            text_segment = segment
            tokens = tokenizer.tokenize(text_segment)
            if len(tokens) > max_tokens:
                chunks = split_text_into_chunks(text_segment, tokenizer, max_tokens)
            else:
                chunks = [text_segment]
            
            annotated_chunks = []
            for chunk in chunks:
                corrected_chunk = fix_grammar(chunk, tokenizer, model, device)
                annotated_chunk = annotate_differences(chunk, corrected_chunk)
                annotated_chunks.append(annotated_chunk)
            # Ghép lại các chunk xử lý của đoạn đó (giữa các chunk mình nối bằng một khoảng trắng đơn)
            annotated_text = "".join(annotated_chunks)
            annotated_segments.append(annotated_text)
    
    # Ghép lại toàn bộ các segment theo đúng thứ tự ban đầu
    return "".join(annotated_segments)

def wrap_words_with_click(text: str) -> str:
    words = text.split()
    return ' '.join(
        f"<span class='word' onclick='scrollToWord({i})'>{w}</span>"
        for i, w in enumerate(words)
    )

def annotated_html_with_ids(original_text: str, annotated_html: str) -> str:
    original_words = original_text.split()
    for i, word in enumerate(original_words):
        annotated_html = re.sub(
            rf"(<span class='(error|suggestion)'[^>]*?>){re.escape(word)}(</span>)",
            rf"\1<span id='suggestion-word-{i}'>\2</span>\3",
            annotated_html,
            count=1
        )
    return annotated_html

def postprocess_annotated_html(annotated_html: str) -> str:
    # Normalize line endings
    normalized = annotated_html.replace('\r\n', '\n')
    # Replace single newlines inside paragraphs with space
    normalized = re.sub(r'(?<!\n)\n(?!\n)', ' ', normalized)
    # Split into paragraphs on double newlines
    paragraphs = normalized.strip().split('\n\n')
    # Wrap with <p> and add spacing
    return ''.join(f"<p style='margin-bottom: 0.75em'>{p.strip()}</p>" for p in paragraphs if p.strip())

async def get_annotated_fixed_essay(answer: str) -> str:
    original_text = answer.strip()
    annotated_html = process_document(original_text, tokenizer, model, device, max_tokens=64)
    annotated_html = annotated_html_with_ids(original_text, annotated_html)
    # 👉 Final post-processing before returning
    annotated_html = postprocess_annotated_html(annotated_html)

    return annotated_html