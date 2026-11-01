"""
Shared tokenizer module for model context counting.
Provides a singleton instance of the HuggingFace AutoTokenizer.
"""

from transformers import AutoTokenizer
from dot.config.paths import TOKENIZER_DIR

# Locate the local tokenizer files directory
_TOKENIZER_PATH = str(TOKENIZER_DIR)

# Module-level singleton instance
_GLOBAL_TOKENIZER = None


def get_tokenizer() -> AutoTokenizer:
    """Returns the shared AutoTokenizer singleton instance.
    
    Loads the tokenizer from disk on the first call.
    Subsequent calls return the cached in-memory instance.
    """
    global _GLOBAL_TOKENIZER
    if _GLOBAL_TOKENIZER is None:
        _GLOBAL_TOKENIZER = AutoTokenizer.from_pretrained(_TOKENIZER_PATH)
    return _GLOBAL_TOKENIZER


def count_tokens(text: str) -> int:
    """Counts the number of tokens in the specified text string."""
    tokenizer = get_tokenizer()
    return len(tokenizer.encode(text))
