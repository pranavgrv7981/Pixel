import re



def sanitize_text_for_speech(text: str, max_chars: int = 1500) -> list[str]:
    """Clean markdown formatting, code fences, and internal markers from assistant text.

    Returns a list of bounded speech segments suitable for sequential TTS.
    """
    if not text or not text.strip():
        return []

    cleaned = text

    # 1. Replace multiline code fences with a spoken placeholder
    cleaned = re.sub(r"```[\w\-]*\n[\s\S]*?```", " Code block omitted. ", cleaned)
    cleaned = re.sub(r"```[\s\S]*?```", " Code block omitted. ", cleaned)

    # 2. Replace inline code backticks
    cleaned = re.sub(r"`([^`]+)`", r"\1", cleaned)

    # 3. Replace markdown images ![alt](url) -> ""
    cleaned = re.sub(r"!\[([^\]]*)\]\([^\)]+\)", "", cleaned)

    # 4. Replace markdown links [text](url) -> text
    cleaned = re.sub(r"\[([^\]]+)\]\([^\)]+\)", r"\1", cleaned)

    # 5. Remove markdown headers (# Title -> Title)
    cleaned = re.sub(r"^#{1,6}\s+", "", cleaned, flags=re.MULTILINE)

    # 6. Remove bold/italic asterisks and underscores (**bold** -> bold, *italic* -> italic)
    cleaned = re.sub(r"\*\*([^\*]+)\*\*", r"\1", cleaned)
    cleaned = re.sub(r"\*([^\*]+)\*", r"\1", cleaned)
    cleaned = re.sub(r"__([^_]+)__", r"\1", cleaned)
    cleaned = re.sub(r"_([^_]+)_", r"\1", cleaned)

    # 7. Clean bullet list markers (* item, - item, 1. item)
    cleaned = re.sub(r"^\s*[\*\-\+]\s+", "", cleaned, flags=re.MULTILINE)
    cleaned = re.sub(r"^\s*\d+\.\s+", "", cleaned, flags=re.MULTILINE)

    # 8. Clean HTML / XML tags
    cleaned = re.sub(r"<[^>]+>", "", cleaned)

    # 9. Clean excessive LaTeX math formatting ($ ... $ -> ...)
    cleaned = re.sub(r"\$\$([^\$]+)\$\$", r"\1", cleaned)

    # 10. Normalize whitespace and punctuation
    cleaned = re.sub(r"[ \t]+", " ", cleaned)
    cleaned = re.sub(r"\s+([.,!?;:])", r"\1", cleaned)
    cleaned = re.sub(r"\n\s*\n+", "\n\n", cleaned).strip()


    if not cleaned:
        return []

    # If the text is within max_chars limit, return as single chunk
    if len(cleaned) <= max_chars:
        return [cleaned]

    # Segment long text at paragraph or sentence boundaries
    segments: list[str] = []
    paragraphs = cleaned.split("\n\n")
    current_chunk = ""

    for p in paragraphs:
        p_clean = p.strip()
        if not p_clean:
            continue

        if len(current_chunk) + len(p_clean) + 2 <= max_chars:
            current_chunk = f"{current_chunk}\n\n{p_clean}".strip() if current_chunk else p_clean
        else:
            if current_chunk:
                segments.append(current_chunk)
                current_chunk = ""

            # If a single paragraph is larger than max_chars, split by sentences
            if len(p_clean) > max_chars:
                sentences = re.split(r"(?<=[.!?])\s+", p_clean)
                for s in sentences:
                    s_clean = s.strip()
                    if not s_clean:
                        continue
                    if len(current_chunk) + len(s_clean) + 1 <= max_chars:
                        current_chunk = f"{current_chunk} {s_clean}".strip() if current_chunk else s_clean
                    else:
                        if current_chunk:
                            segments.append(current_chunk)
                        current_chunk = s_clean
            else:
                current_chunk = p_clean

    if current_chunk:
        segments.append(current_chunk)

    return segments
