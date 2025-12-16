"""
Grammar correction module using COEDIT T5 model.
Fixes grammar errors in essay text and returns corrected text.
"""

import re
import difflib
import torch
from transformers import AutoTokenizer, T5ForConditionalGeneration

# ===========================
# Initialize Model & Tokenizer
# ===========================
device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
tokenizer = AutoTokenizer.from_pretrained("grammarly/coedit-large")
model = T5ForConditionalGeneration.from_pretrained("grammarly/coedit-large").to(device)
print(f"✅ COEDIT Model loaded. Running on device: {device}")


# ===========================
# Core Functions
# ===========================
def fix_grammar(text: str) -> str:
    """
    Fix grammar in the given text using COEDIT T5 model.
    
    Args:
        text: Text to fix
        
    Returns:
        Corrected text
    """
    prompt = "Fix grammar: " + text
    inputs = tokenizer(prompt, return_tensors="pt", truncation=True).to(device)
    outputs = model.generate(inputs.input_ids, max_length=128)
    output_text = tokenizer.decode(outputs[0], skip_special_tokens=True)
    return output_text.strip()


def split_text_into_chunks(text: str, max_tokens: int = 64) -> list:
    """
    Split text into chunks by sentences, each not exceeding max_tokens.
    
    Args:
        text: Text to split
        max_tokens: Maximum tokens per chunk
        
    Returns:
        List of text chunks
    """
    # Split by sentence boundaries (., !, ?)
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


def process_document(text: str, max_tokens: int = 64) -> str:
    """
    Process document and return corrected text.
    
    Preserves paragraph structure (blank lines) and fixes grammar per chunk.
    
    Args:
        text: Document text to process
        max_tokens: Maximum tokens per chunk for processing
        
    Returns:
        Corrected document text
    """
    # Split by paragraph separators (double newlines)
    segments = re.split(r'(\n\s*\n)', text)
    corrected_segments = []
    
    for segment in segments:
        # Keep paragraph separators as-is
        if re.fullmatch(r'\n\s*\n', segment):
            corrected_segments.append(segment)
            continue
        
        # Process text segment
        text_segment = segment.strip()
        if not text_segment:
            continue
        
        # Check if needs chunking
        tokens = tokenizer.tokenize(text_segment)
        if len(tokens) > max_tokens:
            chunks = split_text_into_chunks(text_segment, max_tokens)
        else:
            chunks = [text_segment]
        
        # Fix grammar for each chunk
        corrected_chunks = []
        for chunk in chunks:
            corrected_chunk = fix_grammar(chunk)
            corrected_chunks.append(corrected_chunk)
        
        # Join chunks with space
        corrected_text = " ".join(corrected_chunks)
        corrected_segments.append(corrected_text)
    
    return "".join(corrected_segments)


# ===========================
# API Function
# ===========================
# ===========================
# HTML Wrapping Functions
# ===========================
def wrap_errors_and_fixes(original_text: str, corrected_text: str) -> str:
    """
    Compare original and corrected text, wrap errors in red and fixes in green.
    
    Args:
        original_text: Original (with errors) text
        corrected_text: Corrected text
        
    Returns:
        HTML with errors highlighted in red and fixes in green
    """
    original_words = original_text.split()
    corrected_words = corrected_text.split()
    
    # Compare sequences to find differences
    matcher = difflib.SequenceMatcher(None, original_words, corrected_words)
    opcodes = matcher.get_opcodes()
    
    result_html = ""
    
    for tag, i1, i2, j1, j2 in opcodes:
        if tag == "equal":
            # Same in both - keep as is
            result_html += " ".join(original_words[i1:i2]) + " "
        elif tag == "replace":
            # Different - wrap original in red (error) and corrected in green (fix)
            original_segment = " ".join(original_words[i1:i2])
            corrected_segment = " ".join(corrected_words[j1:j2])
            result_html += (
                f"<span style='background-color: #fee2e2; border-bottom: 2px solid #dc2626; "
                f"padding: 2px 4px; border-radius: 3px;' title='Error'>{original_segment}</span> "
                f"<span style='background-color: #d1fae5; border-bottom: 2px solid #10b981; "
                f"padding: 2px 4px; border-radius: 3px; font-weight: 500;' title='Fix'>→ {corrected_segment}</span> "
            )
        elif tag == "delete":
            # Removed in correction - wrap in red
            deleted_segment = " ".join(original_words[i1:i2])
            result_html += (
                f"<span style='background-color: #fee2e2; border-bottom: 2px solid #dc2626; "
                f"padding: 2px 4px; border-radius: 3px;' title='Error'>{deleted_segment}</span> "
            )
        elif tag == "insert":
            # Added in correction - wrap in green
            added_segment = " ".join(corrected_words[j1:j2])
            result_html += (
                f"<span style='background-color: #d1fae5; border-bottom: 2px solid #10b981; "
                f"padding: 2px 4px; border-radius: 3px; font-weight: 500;' title='Fix'>+ {added_segment}</span> "
            )
    
    return result_html.strip()


def wrap_only_fixes(corrected_text: str) -> str:
    """
    Wrap corrected text with HTML formatting for display (fixes in green).
    Preserves paragraph structure with <p> tags and styles.
    
    Args:
        corrected_text: Corrected text to wrap
        
    Returns:
        HTML formatted text
    """
    if not corrected_text:
        return ""
    
    # Normalize line endings
    normalized = corrected_text.replace('\r\n', '\n')
    
    # Replace single newlines with space (inside paragraphs)
    normalized = re.sub(r'(?<!\n)\n(?!\n)', ' ', normalized)
    
    # Split into paragraphs on double newlines
    paragraphs = normalized.strip().split('\n\n')
    
    # Wrap each paragraph with <p> tag and style
    html_paragraphs = [
        f"<p style='margin-bottom: 0.75em; line-height: 1.8; background: #d1fae5; padding: 10px; "
        f"border-left: 4px solid #10b981; border-radius: 4px;'>{p.strip()}</p>"
        for p in paragraphs
        if p.strip()
    ]
    
    # Combine all paragraphs
    html_content = "".join(html_paragraphs)
    
    return html_content


def wrap_corrected_with_html(text: str) -> str:
    """
    Wrap corrected text with HTML formatting for display.
    Preserves paragraph structure with <p> tags and styles.
    
    Args:
        text: Corrected text to wrap
        
    Returns:
        HTML formatted text
    """
    if not text:
        return ""
    
    # Normalize line endings
    normalized = text.replace('\r\n', '\n')
    
    # Replace single newlines with space (inside paragraphs)
    normalized = re.sub(r'(?<!\n)\n(?!\n)', ' ', normalized)
    
    # Split into paragraphs on double newlines
    paragraphs = normalized.strip().split('\n\n')
    
    # Wrap each paragraph with <p> tag
    html_paragraphs = [
        f"<p style='margin-bottom: 0.75em; line-height: 1.8;'>{p.strip()}</p>"
        for p in paragraphs
        if p.strip()
    ]
    
    # Combine all paragraphs
    html_content = "".join(html_paragraphs)
    
    return html_content


async def get_annotated_fixed_essay(answer: str) -> dict:
    """
    Correct grammar in the essay and return both error+fix view and fixed-only view.
    
    Args:
        answer: The essay text to correct
        
    Returns:
        Dictionary with:
        - 'corrected_text': Plain corrected text
        - 'with_errors': HTML showing errors (red) and fixes (green) side by side
        - 'fixed_only': HTML with just the corrected text (green background)
    """
    if not answer or not answer.strip():
        return {
            'corrected_text': '',
            'with_errors': '',
            'fixed_only': ''
        }
    
    original_text = answer.strip()
    corrected_text = process_document(original_text, max_tokens=64)
    
    # Generate different views
    html_with_errors = wrap_errors_and_fixes(original_text, corrected_text)
    html_fixed_only = wrap_only_fixes(corrected_text)
    
    return {
        'corrected_text': corrected_text,
        'with_errors': html_with_errors,
        'fixed_only': html_fixed_only
    }
