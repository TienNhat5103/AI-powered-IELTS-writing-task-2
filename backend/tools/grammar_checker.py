"""
Grammar correction tool using COEDIT T5.
"""

import asyncio
import difflib
import html
import re
import threading

import torch
from transformers import AutoTokenizer, T5ForConditionalGeneration


MODEL_REPOSITORY = "grammarly/coedit-large"
_runtime = None
_runtime_lock = threading.Lock()
_inference_lock = threading.Lock()


def _load_runtime():
    global _runtime

    if _runtime is not None:
        return _runtime

    with _runtime_lock:
        if _runtime is not None:
            return _runtime

        device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        tokenizer = AutoTokenizer.from_pretrained(MODEL_REPOSITORY)
        model = T5ForConditionalGeneration.from_pretrained(MODEL_REPOSITORY).to(device)
        model.eval()
        _runtime = (device, tokenizer, model)

    return _runtime


def fix_grammar(text: str) -> str:
    device, tokenizer, model = _load_runtime()
    prompt = "Fix grammar: " + text
    inputs = tokenizer(prompt, return_tensors="pt", truncation=True).to(device)
    with _inference_lock:
        with torch.no_grad():
            outputs = model.generate(inputs.input_ids, max_length=128)
    output_text = tokenizer.decode(outputs[0], skip_special_tokens=True)
    return output_text.strip()


def split_text_into_chunks(text: str, max_tokens: int = 64) -> list:
    _, tokenizer, _ = _load_runtime()
    sentences = re.split(r"(?<=[.!?])\s+", text)
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


def process_document(text: str, max_tokens: int = 64) -> str:
    _, tokenizer, _ = _load_runtime()
    segments = re.split(r"(\n\s*\n)", text)
    corrected_segments = []

    for segment in segments:
        if re.fullmatch(r"\n\s*\n", segment):
            corrected_segments.append(segment)
            continue

        text_segment = segment.strip()
        if not text_segment:
            continue

        tokens = tokenizer.tokenize(text_segment)
        if len(tokens) > max_tokens:
            chunks = split_text_into_chunks(text_segment, max_tokens)
        else:
            chunks = [text_segment]

        corrected_chunks = []
        for chunk in chunks:
            corrected_chunks.append(fix_grammar(chunk))

        corrected_segments.append(" ".join(corrected_chunks))

    return "".join(corrected_segments)


def wrap_errors_and_fixes(original_text: str, corrected_text: str) -> str:
    original_words = original_text.split()
    corrected_words = corrected_text.split()
    matcher = difflib.SequenceMatcher(None, original_words, corrected_words)
    result_html = ""

    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == "equal":
            result_html += html.escape(" ".join(original_words[i1:i2])) + " "
        elif tag == "replace":
            original_segment = html.escape(" ".join(original_words[i1:i2]))
            corrected_segment = html.escape(" ".join(corrected_words[j1:j2]))
            result_html += (
                f"<span style='background-color: #fee2e2; border-bottom: 2px solid #dc2626; "
                f"padding: 2px 4px; border-radius: 3px;' title='Error'>{original_segment}</span> "
                f"<span style='background-color: #d1fae5; border-bottom: 2px solid #10b981; "
                f"padding: 2px 4px; border-radius: 3px; font-weight: 500;' title='Fix'>-> {corrected_segment}</span> "
            )
        elif tag == "delete":
            deleted_segment = html.escape(" ".join(original_words[i1:i2]))
            result_html += (
                f"<span style='background-color: #fee2e2; border-bottom: 2px solid #dc2626; "
                f"padding: 2px 4px; border-radius: 3px;' title='Error'>{deleted_segment}</span> "
            )
        elif tag == "insert":
            added_segment = html.escape(" ".join(corrected_words[j1:j2]))
            result_html += (
                f"<span style='background-color: #d1fae5; border-bottom: 2px solid #10b981; "
                f"padding: 2px 4px; border-radius: 3px; font-weight: 500;' title='Fix'>+ {added_segment}</span> "
            )

    return result_html.strip()


def wrap_only_fixes(corrected_text: str) -> str:
    if not corrected_text:
        return ""

    normalized = corrected_text.replace("\r\n", "\n")
    normalized = re.sub(r"(?<!\n)\n(?!\n)", " ", normalized)
    paragraphs = normalized.strip().split("\n\n")

    html_paragraphs = [
        f"<p style='margin-bottom: 0.75em; line-height: 1.8; background: #d1fae5; padding: 10px; "
        f"border-left: 4px solid #10b981; border-radius: 4px;'>{html.escape(paragraph.strip())}</p>"
        for paragraph in paragraphs
        if paragraph.strip()
    ]

    return "".join(html_paragraphs)


def wrap_corrected_with_html(text: str) -> str:
    if not text:
        return ""

    normalized = text.replace("\r\n", "\n")
    normalized = re.sub(r"(?<!\n)\n(?!\n)", " ", normalized)
    paragraphs = normalized.strip().split("\n\n")

    html_paragraphs = [
        f"<p style='margin-bottom: 0.75em; line-height: 1.8;'>{html.escape(paragraph.strip())}</p>"
        for paragraph in paragraphs
        if paragraph.strip()
    ]

    return "".join(html_paragraphs)


async def get_annotated_fixed_essay(answer: str) -> dict:
    if not answer or not answer.strip():
        return {
            "corrected_text": "",
            "with_errors": "",
            "fixed_only": "",
        }

    original_text = answer.strip()
    corrected_text = await asyncio.to_thread(process_document, original_text, 64)

    return {
        "corrected_text": corrected_text,
        "with_errors": wrap_errors_and_fixes(original_text, corrected_text),
        "fixed_only": wrap_only_fixes(corrected_text),
    }


async def check_grammar(answer: str) -> dict:
    """Return corrected essay text and HTML annotation views."""
    return await get_annotated_fixed_essay(answer)
