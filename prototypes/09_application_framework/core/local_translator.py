"""
core/local_translator.py

LingoLens Local Translation Engine

Provides local/offline translation using the NLLB-200 distilled 600M
CTranslate2 INT8 model.

The implementation is based on the validated NLLB test workflow:
    - CTranslate2 CPU inference
    - INT8 compute
    - SentencePiece tokenization
    - Per-item NLLB source language tokens
    - NLLB target language prefix
    - Batched translation
    - Beam size 2
    - Maximum decoding length 256

The model is intentionally kept outside the LingoLens repository
during the initial integration phase.
"""

from __future__ import annotations

import os
import threading
from pathlib import Path

import ctranslate2
import sentencepiece


# --------------------------------------------------
# Module configuration
# --------------------------------------------------

MODULE = "LOCAL_TRANSLATOR"


# --------------------------------------------------
# NLLB configuration
# --------------------------------------------------

DEFAULT_MODEL_PATH = (
    r"C:\Users\harish.singh.bisht\LL\nllb-600m-ct2-int8"
)

MODEL_PATH = os.environ.get(
    "LINGOLENS_NLLB_MODEL_PATH",
    DEFAULT_MODEL_PATH,
)

TARGET_LANGUAGE = "eng_Latn"

BEAM_SIZE = 2

MAX_DECODING_LENGTH = 256


# --------------------------------------------------
# LingoLens language mapping
# --------------------------------------------------

NLLB_LANGUAGE_MAP = {
    "english": "eng_Latn",
    "en": "eng_Latn",

    "hindi": "hin_Deva",
    "hi": "hin_Deva",

    "japanese": "jpn_Jpan",
    "ja": "jpn_Jpan",

    "chinese": "zho_Hans",
    "zh": "zho_Hans",
    "zh-cn": "zho_Hans",
    "chinese simplified": "zho_Hans",

    "russian": "rus_Cyrl",
    "ru": "rus_Cyrl",

    "german": "deu_Latn",
    "de": "deu_Latn",

    "french": "fra_Latn",
    "fr": "fra_Latn",

    "sanskrit": "san_Deva",
    "sa": "san_Deva",
}


# --------------------------------------------------
# Model state
# --------------------------------------------------

_TRANSLATOR = None

_TOKENIZER = None

_MODEL_LOCK = threading.Lock()


# --------------------------------------------------
# Language helpers
# --------------------------------------------------


def normalize_language_code(language: str) -> str:
    """
    Convert a LingoLens language name/code into an NLLB language code.

    Returns an empty string when the language is not configured.
    """
    if not language:
        return ""

    normalized = str(language).strip().lower()

    return NLLB_LANGUAGE_MAP.get(
        normalized,
        normalized,
    )


# --------------------------------------------------
# Model loading
# --------------------------------------------------


def _validate_model_path() -> Path:
    """
    Validate that the configured NLLB model directory exists.
    """
    model_path = Path(MODEL_PATH)

    if not model_path.exists():
        raise FileNotFoundError(
            "NLLB model directory does not exist: "
            f"{model_path}"
        )

    if not model_path.is_dir():
        raise NotADirectoryError(
            "NLLB model path is not a directory: "
            f"{model_path}"
        )

    model_file = model_path / "model.bin"

    if not model_file.exists():
        raise FileNotFoundError(
            "NLLB model.bin was not found: "
            f"{model_file}"
        )

    tokenizer_file = (
        model_path / "sentencepiece.bpe.model"
    )

    if not tokenizer_file.exists():
        raise FileNotFoundError(
            "NLLB SentencePiece model was not found: "
            f"{tokenizer_file}"
        )

    return model_path


def _load_model():
    """
    Load and cache the NLLB translator and tokenizer.

    Model loading is performed only once for the process.
    """
    global _TRANSLATOR
    global _TOKENIZER

    if (
        _TRANSLATOR is not None
        and _TOKENIZER is not None
    ):
        return (
            _TRANSLATOR,
            _TOKENIZER,
        )

    with _MODEL_LOCK:

        if (
            _TRANSLATOR is not None
            and _TOKENIZER is not None
        ):
            return (
                _TRANSLATOR,
                _TOKENIZER,
            )

        model_path = _validate_model_path()

        _TRANSLATOR = ctranslate2.Translator(
            str(model_path),
            device="cpu",
            compute_type="int8",
        )

        _TOKENIZER = sentencepiece.SentencePieceProcessor(
            model_file=str(
                model_path / "sentencepiece.bpe.model"
            )
        )

        return (
            _TRANSLATOR,
            _TOKENIZER,
        )


# --------------------------------------------------
# Token preparation
# --------------------------------------------------


def _prepare_source_tokens(
    tokenizer,
    source_language: str,
    text: str,
) -> list[str]:
    """
    Prepare one NLLB source sequence.

    NLLB requires the source language token before the
    SentencePiece tokens and the end-of-sequence token
    after the source text.
    """
    tokens = tokenizer.encode(
        text,
        out_type=str,
    )

    return [
        source_language,
        *tokens,
        "</s>",
    ]


# --------------------------------------------------
# Output decoding
# --------------------------------------------------


def _decode_translation(
    tokenizer,
    result,
) -> str:
    """
    Decode the best NLLB hypothesis into normal text.
    """
    target_tokens = result.hypotheses[0]

    if (
        target_tokens
        and target_tokens[0] == TARGET_LANGUAGE
    ):
        target_tokens = target_tokens[1:]

    translation = tokenizer.decode(
        target_tokens
    )

    return str(
        translation
    ).strip()


# --------------------------------------------------
# Single translation
# --------------------------------------------------


def translate_text(
    text: str,
    source: str,
    target: str = TARGET_LANGUAGE,
) -> str:
    """
    Translate one text using the local NLLB model.

    Parameters
    ----------
    text:
        Source text.

    source:
        LingoLens language name/code or NLLB language code.

    target:
        LingoLens language name/code or NLLB language code.

    Returns
    -------
    str
        Translated text.

    Raises
    ------
    ValueError
        When source/target language configuration is invalid.

    FileNotFoundError
        When the NLLB model is unavailable.
    """
    if not text or not str(text).strip():
        return ""

    source_language = normalize_language_code(
        source
    )

    target_language = normalize_language_code(
        target
    )

    if not source_language:
        raise ValueError(
            "Local translation source language is not configured."
        )

    if not target_language:
        raise ValueError(
            "Local translation target language is not configured."
        )

    if source_language == target_language:
        return str(text).strip()

    translator, tokenizer = _load_model()

    source_tokens = _prepare_source_tokens(
        tokenizer,
        source_language,
        str(text).strip(),
    )

    target_prefix = [
        target_language
    ]

    results = translator.translate_batch(
        [source_tokens],
        target_prefix=[target_prefix],
        beam_size=BEAM_SIZE,
        max_decoding_length=MAX_DECODING_LENGTH,
    )

    if not results:
        return ""

    return _decode_translation(
        tokenizer,
        results[0],
    )


# --------------------------------------------------
# Batch translation
# --------------------------------------------------


def translate_text_batch(
    texts,
    source,
    target: str = TARGET_LANGUAGE,
) -> list[str]:
    """
    Translate multiple text blocks using one NLLB batch.

    Each item may use a different source language when
    source is supplied as a sequence of language codes.

    For a normal LingoLens batch, source may be one language
    shared by all text blocks.

    Parameters
    ----------
    texts:
        Sequence of source text blocks.

    source:
        One source language shared by all items, or a sequence
        containing one source language per item.

    target:
        Target language.

    Returns
    -------
    list[str]
        Translations in the same order as the input texts.
    """
    if not texts:
        return []

    normalized_texts = []

    for text in texts:
        if text is None:
            normalized_texts.append("")
        else:
            normalized_texts.append(
                str(text).strip()
            )

    if not any(
        text
        for text in normalized_texts
    ):
        return [
            ""
            for _ in normalized_texts
        ]

    target_language = normalize_language_code(
        target
    )

    if not target_language:
        raise ValueError(
            "Local translation target language is not configured."
        )

    if isinstance(source, (list, tuple)):
        if len(source) != len(normalized_texts):
            raise ValueError(
                "Source language sequence length must match "
                "the number of text blocks."
            )

        source_languages = [
            normalize_language_code(language)
            for language in source
        ]

    else:
        normalized_source = normalize_language_code(
            source
        )

        source_languages = [
            normalized_source
            for _ in normalized_texts
        ]

    for source_language in source_languages:
        if not source_language:
            raise ValueError(
                "Local translation source language is not configured."
            )

    translator, tokenizer = _load_model()

    source_batch = []

    for source_language, text in zip(
        source_languages,
        normalized_texts,
    ):
        if not text:
            source_batch.append(
                [
                    source_language,
                    "</s>",
                ]
            )
            continue

        source_tokens = _prepare_source_tokens(
            tokenizer,
            source_language,
            text,
        )

        source_batch.append(
            source_tokens
        )

    target_prefix = [
        [target_language]
        for _ in normalized_texts
    ]

    results = translator.translate_batch(
        source_batch,
        target_prefix=target_prefix,
        beam_size=BEAM_SIZE,
        max_decoding_length=MAX_DECODING_LENGTH,
    )

    translations = []

    for index, result in enumerate(results):

        if not normalized_texts[index]:
            translations.append("")
            continue

        translations.append(
            _decode_translation(
                tokenizer,
                result,
            )
        )

    return translations


# --------------------------------------------------
# Model status
# --------------------------------------------------


def is_available() -> bool:
    """
    Return True when the configured NLLB model files exist.
    """
    try:
        _validate_model_path()
    except (
        FileNotFoundError,
        NotADirectoryError,
    ):
        return False

    return True


def get_model_path() -> str:
    """
    Return the currently configured NLLB model path.
    """
    return str(
        Path(MODEL_PATH)
    )