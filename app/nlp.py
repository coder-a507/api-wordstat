from collections import Counter
from typing import Dict, List, Tuple

import spacy

_nlp = spacy.load("en_core_web_sm")

MAX_TEXT_LENGTH = _nlp.max_length


class TextTooLongError(ValueError):
    """Raised when input text exceeds MAX_TEXT_LENGTH characters."""


def _content_tokens(text: str):
    """Yield the spaCy tokens that count as words.

    Shared by extract_lemmas and extract_word_stats so the length guard and
    the token filter can't drift apart. The length check runs on first
    iteration (before spaCy sees the text), so it stays instant on huge input.
    """
    if len(text) > MAX_TEXT_LENGTH:
        raise TextTooLongError(
            f"text is {len(text)} characters, which exceeds the "
            f"{MAX_TEXT_LENGTH}-character limit"
        )
    for token in _nlp(text):
        if token.is_alpha and not token.like_num:
            yield token


def extract_lemmas(text: str) -> Dict[str, int]:
    counts = Counter(token.lemma_.lower() for token in _content_tokens(text))
    return dict(sorted(counts.items()))


# Closed-class function words. spaCy's POS tags don't map cleanly onto these
# categories (it tags possessives as PRON, "other"/"much" as ADJ, "no" as
# INTJ, ...), so they're resolved by lemma before the POS map. The word lists
# and label strings are taken verbatim from the external dictionary DB's
# `t` column.
_CLOSED_CLASS_LABELS: Dict[str, str] = {
    "the": "art.",
    "a": "art.",
    "that": "dem. det.",
    "this": "dem. det.",
    "these": "dem. det.",
    "those": "dem. det.",
    "his": "poss. det.",
    "her": "poss. det.",
    "their": "poss. det.",
    "my": "poss. det.",
    "our": "poss. det.",
    "its": "poss. det.",
    "your": "definition",
    "what": "definition",
    "no": "definition",
    "other": "definition",
    "any": "definition",
    "much": "definition",
    "all": "definition",
    "another": "definition",
    "some": "definition",
    "more": "definition",
    "few": "definition",
    "which": "definition",
    "every": "definition",
    "both": "definition",
    "many": "definition",
    "enough": "definition",
    "several": "definition",
    "each": "definition",
    "neither": "definition",
    "least": "definition",
}

# spaCy coarse POS (token.pos_) -> DB label, for the cases with no extra
# condition. AUX is handled separately (modal vs. non-modal); anything not
# here and not AUX falls through to the lowercased spaCy tag.
_UPOS_LABELS: Dict[str, str] = {
    "ADJ": "adjective",
    "ADV": "adverb",
    "NOUN": "noun",
    "PROPN": "proper noun",
    "VERB": "verb",
    "NUM": "numeral",
    "ADP": "prep.",
    "PRON": "pronoun",
    "CCONJ": "conj.",
    "SCONJ": "conj.",
    "DET": "det.",
}


def _word_label(token) -> Tuple[str, str]:
    """Return (lemma, pos_label) for one token."""
    surface = "a" if token.lower_ == "an" else token.lower_
    if surface in _CLOSED_CLASS_LABELS:
        return surface, _CLOSED_CLASS_LABELS[surface]

    lemma = token.lemma_.lower()
    if lemma in _CLOSED_CLASS_LABELS:
        return lemma, _CLOSED_CLASS_LABELS[lemma]

    if token.pos_ == "AUX":
        return lemma, "modal verb" if token.tag_ == "MD" else "verb"
    return lemma, _UPOS_LABELS.get(token.pos_, token.pos_.lower())


def extract_word_stats(text: str) -> List[dict]:
    counts = Counter(_word_label(token) for token in _content_tokens(text))
    return [
        {"lemma": lemma, "pos": pos, "count": n}
        for (lemma, pos), n in sorted(counts.items())
    ]
