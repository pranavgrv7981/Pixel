"""Unit tests for text-to-speech text sanitization and segmentation."""

from app.voice.text_sanitizer import sanitize_text_for_speech


def test_sanitize_empty_and_whitespace() -> None:
    assert sanitize_text_for_speech("") == []
    assert sanitize_text_for_speech("   \n\t  ") == []


def test_sanitize_markdown_formatting() -> None:
    raw = "The total value is **$250.00** and the status is *confirmed*."
    segments = sanitize_text_for_speech(raw)
    assert len(segments) == 1
    assert "**" not in segments[0]
    assert "*" not in segments[0]
    assert "The total value is $250.00 and the status is confirmed." in segments[0]



def test_sanitize_code_blocks() -> None:
    raw = (
        "Here is the solution to your request:\n\n"
        "```python\ndef add(a, b):\n    return a + b\n```\n\n"
        "You can run this function directly."
    )
    segments = sanitize_text_for_speech(raw)
    assert len(segments) == 1
    assert "def add" not in segments[0]
    assert "Code block omitted." in segments[0]
    assert "You can run this function directly." in segments[0]


def test_sanitize_headers_and_lists() -> None:
    raw = (
        "# System Health Report\n"
        "## Summary\n"
        "* CPU usage: 15%\n"
        "* Memory usage: 45%\n"
        "1. First step\n"
        "2. Second step\n"
    )
    segments = sanitize_text_for_speech(raw)
    assert len(segments) == 1
    assert "#" not in segments[0]
    assert "System Health Report" in segments[0]
    assert "CPU usage: 15%" in segments[0]
    assert "First step" in segments[0]


def test_sanitize_links_and_html() -> None:
    raw = 'Check out [Ollama Documentation](https://ollama.com) for <span style="color:red;">details</span>.'
    segments = sanitize_text_for_speech(raw)
    assert len(segments) == 1
    assert "https://ollama.com" not in segments[0]
    assert "<span" not in segments[0]
    assert "Check out Ollama Documentation for details." in segments[0]


def test_segmentation_for_long_texts() -> None:
    p1 = "First paragraph with introductory text. " * 5
    p2 = "Second paragraph detailing the complete analysis. " * 5
    p3 = "Third paragraph summarizing key findings. " * 5
    full_text = f"{p1}\n\n{p2}\n\n{p3}"

    segments = sanitize_text_for_speech(full_text, max_chars=200)
    assert len(segments) >= 3
    for s in segments:
        assert len(s) <= 250
