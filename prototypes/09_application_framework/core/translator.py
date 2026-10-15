"""
core/translator.py

LingoLens Translation Engine

Provides reusable functions for translating text.

The translation engine is provider-independent and designed to
handle local and external translation-service failures gracefully.

Current providers:
    - Local NLLB Translation (primary)
    - MyMemory (fallback)
    - GoogleTranslator (fallback)

The public API remains:
    - translate_text()
    - translate_text_batch()
"""

from __future__ import annotations

import threading
import time
from concurrent.futures import ThreadPoolExecutor

import requests
from deep_translator import GoogleTranslator
from langdetect import DetectorFactory, LangDetectException, detect

from config import (
    DEFAULT_SOURCE_LANGUAGE,
    DEFAULT_TARGET_LANGUAGE,
)

from logger import logger

from core.local_translator import (
    is_available as is_local_translation_available,
    translate_text as local_translate_text,
    translate_text_batch as local_translate_text_batch,
)


MODULE = "TRANSLATOR"


# --------------------------------------------------
# Translation configuration
# --------------------------------------------------

TRANSLATION_TIMEOUТ = 8.0

TRANSLATION_RETRIES = 1

TRANSLATION_RETRY_DELAY = 1.0

# Maximum number of translations allowed to run concurrently
# for external provider recovery.
TRANSLATION_MAX_WORKERS = 2

# Recovery passes for failed batch items.
TRANSLATION_BATCH_RECOVERY_RETRIES = 1

TRANSLATION_BATCH_RECOVERY_DELAY = 1.0


# --------------------------------------------------
# Provider configuration
# --------------------------------------------------

# Local NLLB translation is now the primary provider.
#
# MyMemory and Google remain available as fallbacks.
#
# The local provider does not require an internet connection
# once the model is available.

LOCAL_PROVIDER_ENABLED = True

MYMEMORY_BASE_URL = (
    "https://api.mymemory.translated.net/get"
)

MYMEMORY_TIMEOUT = 8.0

MYMEMORY_USER_AGENT = (
    "LingoLens/0.9 "
    "(Translation Service)"
)

GOOGLE_PROVIDER_ENABLED = True


# --------------------------------------------------
# Provider health / cooldown
# --------------------------------------------------

PROVIDER_COOLDOWN_SECONDS = 30.0

_PROVIDER_HEALTH_LOCK = threading.Lock()

_PROVIDER_UNAVAILABLE_UNTIL = {}


# --------------------------------------------------
# Translator instance cache
# --------------------------------------------------

_TRANSLATOR_THREAD_LOCAL = threading.local()


# --------------------------------------------------
# MyMemory HTTP session cache
# --------------------------------------------------

_MYMEMORY_THREAD_LOCAL = threading.local()


# --------------------------------------------------
# Translation result cache
# --------------------------------------------------

_TRANSLATION_CACHE = {}

_TRANSLATION_CACHE_LOCK = threading.Lock()


# --------------------------------------------------
# Language detection configuration
# --------------------------------------------------

# Make langdetect deterministic so the same OCR text does
# not randomly produce different language results.

DetectorFactory.seed = 0


# --------------------------------------------------
# Language mapping
# --------------------------------------------------

_LANGUAGE_CODE_MAP = {
    "auto": "auto",
    "english": "en",
    "en": "en",
    "hindi": "hi",
    "hi": "hi",
    "japanese": "ja",
    "ja": "ja",
    "chinese": "zh-CN",
    "chinese simplified": "zh-CN",
    "zh": "zh-CN",
    "zh-cn": "zh-CN",
    "russian": "ru",
    "ru": "ru",
    "german": "de",
    "de": "de",
    "french": "fr",
    "fr": "fr",
    "sanskrit": "sa",
    "sa": "sa",
}


# --------------------------------------------------
# NLLB-supported language codes
# --------------------------------------------------

# These are the languages currently exposed by
# core.local_translator.py.
#
# Keeping this list here prevents langdetect results such as
# "ro" or "ar" from being passed blindly to NLLB when the
# installed model configuration does not expose those mappings.

_LOCAL_LANGUAGE_CODES = {
    "en",
    "hi",
    "ja",
    "zh-CN",
    "ru",
    "de",
    "fr",
    "sa",
}


# --------------------------------------------------
# Provider health helpers
# --------------------------------------------------


def _is_provider_available(provider_name):
    """
    Return True when a provider is currently available.

    Providers placed into cooldown after provider-level failures
    are temporarily skipped to avoid unnecessary requests.
    """
    now = time.monotonic()

    with _PROVIDER_HEALTH_LOCK:

        unavailable_until = (
            _PROVIDER_UNAVAILABLE_UNTIL.get(
                provider_name,
                0.0,
            )
        )

        if now >= unavailable_until:

            if provider_name in _PROVIDER_UNAVAILABLE_UNTIL:
                del _PROVIDER_UNAVAILABLE_UNTIL[
                    provider_name
                ]

            return True

        return False


def _mark_provider_failure(provider_name):
    """
    Temporarily place a provider into cooldown.

    This should only be called for provider/system-level
    failures, not for individual OCR or language-detection
    problems.
    """
    unavailable_until = (
        time.monotonic()
        + PROVIDER_COOLDOWN_SECONDS
    )

    with _PROVIDER_HEALTH_LOCK:

        _PROVIDER_UNAVAILABLE_UNTIL[
            provider_name
        ] = unavailable_until

    logger.warning(
        MODULE,
        (
            f"Translation provider '{provider_name}' "
            f"placed in cooldown for "
            f"{PROVIDER_COOLDOWN_SECONDS:.0f} seconds."
        ),
    )


def _mark_provider_success(provider_name):
    """
    Clear provider cooldown after a successful request.
    """
    with _PROVIDER_HEALTH_LOCK:

        _PROVIDER_UNAVAILABLE_UNTIL.pop(
            provider_name,
            None,
        )


# --------------------------------------------------
# Response validation
# --------------------------------------------------


def _is_invalid_translation_response(
    translated_text,
):
    """
    Check whether the translation service returned an invalid
    or known error response instead of a real translation.
    """
    if translated_text is None:
        return True

    normalized = str(
        translated_text
    ).strip().lower()

    if not normalized:
        return True

    error_markers = (
        "error 500",
        "server error",
        "there was an error",
        "please try again later",
        "that's all we know",
        "that’s all we know",
        "too many requests",
        "quota exceeded",
        "rate limit",
    )

    return any(
        marker in normalized
        for marker in error_markers
    )


# --------------------------------------------------
# Language helpers
# --------------------------------------------------


def _normalize_language_code(language):
    """
    Convert a LingoLens language name/code into an ISO-style
    language code suitable for external providers.
    """
    if not language:
        return ""

    normalized = str(
        language
    ).strip().lower()

    return _LANGUAGE_CODE_MAP.get(
        normalized,
        normalized,
    )


def _detect_script_language(text):
    """
    Detect languages that can be identified reliably from
    Unicode script characteristics.

    This is intentionally performed before langdetect because
    OCR frequently produces short or fragmented text for which
    statistical language detection is unreliable.

    Returns
    -------
    str
        Normalized LingoLens language code, or "" when the
        script is not sufficiently distinctive.
    """
    if not text or not text.strip():
        return ""

    japanese_count = 0
    hindi_count = 0
    chinese_count = 0

    for character in text:

        code_point = ord(character)

        # Hiragana
        if 0x3040 <= code_point <= 0x309F:
            japanese_count += 1
            continue

        # Katakana
        if 0x30A0 <= code_point <= 0x30FF:
            japanese_count += 1
            continue

        # Katakana phonetic extensions
        if 0x31F0 <= code_point <= 0x31FF:
            japanese_count += 1
            continue

        # Devanagari
        if 0x0900 <= code_point <= 0x097F:
            hindi_count += 1
            continue

        # CJK Unified Ideographs.
        #
        # These can represent either Chinese or Japanese Kanji.
        # We only count them here and resolve Japanese first when
        # Japanese kana are also present.
        if (
            0x3400 <= code_point <= 0x4DBF
            or 0x4E00 <= code_point <= 0x9FFF
            or 0xF900 <= code_point <= 0xFAFF
        ):
            chinese_count += 1

    if japanese_count > 0:
        return "ja"

    if hindi_count > 0:
        return "hi"

    if chinese_count > 0:
        return "zh-CN"

    return ""


def _detect_source_language(text):
    """
    Detect the source language locally.

    Script-based detection is used first for languages with
    distinctive Unicode ranges. langdetect is used as a fallback
    for languages that primarily use Latin/Cyrillic scripts.

    Returns
    -------
    str
        Normalized language code suitable for providers.

    Returns an empty string when detection is not reliable.
    """
    if not text or not text.strip():
        return ""

    script_language = _detect_script_language(
        text
    )

    if script_language:

        logger.info(
            MODULE,
            (
                "Automatic source language detected by "
                f"Unicode script: {script_language}."
            ),
        )

        return script_language

    try:

        detected_language = detect(
            text.strip()
        )

    except LangDetectException as error:

        logger.warning(
            MODULE,
            (
                "Automatic language detection failed: "
                f"{error}"
            ),
        )

        return ""

    except Exception as error:

        logger.warning(
            MODULE,
            (
                "Automatic language detection encountered "
                f"an unexpected error: {error}"
            ),
        )

        return ""

    normalized_language = (
        _normalize_language_code(
            detected_language
        )
    )

    # langdetect uses zh for Chinese. External providers
    # in this module use zh-CN for Simplified Chinese.
    if normalized_language == "zh":
        normalized_language = "zh-CN"

    logger.info(
        MODULE,
        (
            "Automatic source language detected: "
            f"{detected_language} -> "
            f"{normalized_language}."
        ),
    )

    return normalized_language


def _resolve_source_language(
    text,
    source,
):
    """
    Resolve an explicit or automatic source language.

    Returns
    -------
    str
        Resolved normalized language code.

    Raises
    ------
    RuntimeError
        When automatic detection fails.
    """
    source_code = _normalize_language_code(
        source
    )

    if source_code == "auto":

        source_code = _detect_source_language(
            text
        )

        if not source_code:

            raise RuntimeError(
                "Automatic source language detection failed."
            )

    return source_code


def _expand_batch_sources(
    source,
    item_count,
):
    """
    Normalize the batch source argument.

    A single source language applies to every item.

    A sequence of source languages provides one source
    language per text item.
    """
    if isinstance(
        source,
        str,
    ) or source is None:

        return [
            source
            for _ in range(item_count)
        ]

    try:

        source_values = list(source)

    except TypeError as error:

        raise ValueError(
            "Batch source must be a language string or "
            "a sequence of language strings."
        ) from error

    if len(source_values) != item_count:

        raise ValueError(
            "Batch source sequence length must match "
            "the number of text blocks."
        )

    return source_values


# --------------------------------------------------
# Google translator cache
# --------------------------------------------------


def _get_translator(source, target):
    """
    Return a reusable GoogleTranslator instance for the
    requested source/target language pair.

    Instances are cached per persistent worker thread.
    """
    source_key = (
        str(source).strip().lower()
        if source
        else ""
    )

    target_key = (
        str(target).strip().lower()
        if target
        else ""
    )

    cache_key = (
        source_key,
        target_key,
    )

    translator_cache = getattr(
        _TRANSLATOR_THREAD_LOCAL,
        "translators",
        None,
    )

    if translator_cache is None:

        translator_cache = {}

        _TRANSLATOR_THREAD_LOCAL.translators = (
            translator_cache
        )

    translator = translator_cache.get(
        cache_key
    )

    if translator is None:

        translator = GoogleTranslator(
            source=source,
            target=target,
        )

        translator_cache[cache_key] = (
            translator
        )

        logger.info(
            MODULE,
            (
                "Created thread-local reusable "
                "GoogleTranslator for "
                f"{source}->{target}."
            ),
        )

    return translator


# --------------------------------------------------
# MyMemory HTTP session
# --------------------------------------------------


def _get_mymemory_session():
    """
    Return a reusable MyMemory requests session for the
    current worker thread.
    """
    session = getattr(
        _MYMEMORY_THREAD_LOCAL,
        "session",
        None,
    )

    if session is None:

        session = requests.Session()

        session.headers.update(
            {
                "User-Agent": MYMEMORY_USER_AGENT,
                "Accept": "application/json",
            }
        )

        _MYMEMORY_THREAD_LOCAL.session = session

    return session


# --------------------------------------------------
# Translation cache helpers
# --------------------------------------------------


def _get_translation_cache_key(
    text,
    source,
    target,
):
    """
    Build the cache key for a translation result.
    """
    return (
        str(source).strip().lower()
        if source
        else "",
        str(target).strip().lower()
        if target
        else "",
        text.strip(),
    )


def _get_cached_translation(
    text,
    source,
    target,
):
    """
    Return a cached translation if available.

    Returns
    -------
    tuple
        (found, translation)
    """
    cache_key = _get_translation_cache_key(
        text,
        source,
        target,
    )

    with _TRANSLATION_CACHE_LOCK:

        if cache_key in _TRANSLATION_CACHE:

            return (
                True,
                _TRANSLATION_CACHE[cache_key],
            )

    return (
        False,
        "",
    )


def _store_cached_translation(
    text,
    source,
    target,
    translated_text,
):
    """
    Store a successful translation in the in-memory cache.
    """
    cache_key = _get_translation_cache_key(
        text,
        source,
        target,
    )

    with _TRANSLATION_CACHE_LOCK:

        _TRANSLATION_CACHE[cache_key] = (
            translated_text
        )


# --------------------------------------------------
# Local NLLB provider
# --------------------------------------------------


def _translate_with_local(
    text,
    source,
    target,
):
    """
    Translate one text using the local NLLB engine.

    This function is retained for single-text translation
    and fallback/recovery.

    IMPORTANT:
        Individual text/language errors do not put the local
        provider into cooldown. Only model/provider-level
        failures do that.

    Returns
    -------
    tuple
        (translated_text, error)
    """
    if not LOCAL_PROVIDER_ENABLED:

        return (
            None,
            RuntimeError(
                "Local translation provider is disabled."
            ),
        )

    if not _is_provider_available(
        "local"
    ):

        return (
            None,
            RuntimeError(
                "Local translation provider is in cooldown."
            ),
        )

    try:

        if not is_local_translation_available():

            error = RuntimeError(
                "Local NLLB translation model is unavailable."
            )

            _mark_provider_failure(
                "local"
            )

            return (
                None,
                error,
            )

        source_code = _resolve_source_language(
            text,
            source,
        )

        target_code = _normalize_language_code(
            target
        )

        if not source_code:

            return (
                None,
                RuntimeError(
                    "Source language is not configured."
                ),
            )

        if source_code not in _LOCAL_LANGUAGE_CODES:

            return (
                None,
                RuntimeError(
                    (
                        "Local NLLB does not currently "
                        f"support source language '{source_code}'."
                    )
                ),
            )

        if not target_code:

            return (
                None,
                RuntimeError(
                    "Target language is not configured."
                ),
            )

        translated_text = local_translate_text(
            text,
            source_code,
            target_code,
        )

        if _is_invalid_translation_response(
            translated_text
        ):

            return (
                None,
                RuntimeError(
                    "Local NLLB returned an invalid translation."
                ),
            )

        translated_text = str(
            translated_text
        ).strip()

        _mark_provider_success(
            "local"
        )

        return (
            translated_text,
            None,
        )

    except RuntimeError as error:

        # RuntimeError is normally an item-level problem such as
        # unsupported language or automatic detection failure.
        #
        # Do NOT globally disable NLLB for this.
        return (
            None,
            error,
        )

    except Exception as error:

        # Unexpected failures are treated as provider/model-level
        # failures and therefore can trigger cooldown.
        _mark_provider_failure(
            "local"
        )

        return (
            None,
            error,
        )


def _translate_with_local_batch(
    texts,
    sources,
    target,
):
    """
    Translate a batch using one NLLB translate_batch call.

    This is the primary Live Mode path.

    Parameters
    ----------
    texts : sequence[str]
        Text blocks to translate.

    sources : sequence[str]
        One source language per text item.

    target : str
        Target language.

    Returns
    -------
    tuple
        (translations, errors)

        translations:
            One translation string per input item.

        errors:
            One error object or None per input item.

    Notes
    -----
    - Source languages are resolved individually.
    - Japanese/Hindi/etc. are identified using Unicode script
      detection before langdetect.
    - A bad individual OCR item does not put NLLB into cooldown.
    - A genuine model/provider failure can put NLLB into cooldown.
    """
    item_count = len(texts)

    translations = [
        ""
        for _ in range(item_count)
    ]

    errors = [
        None
        for _ in range(item_count)
    ]

    if not LOCAL_PROVIDER_ENABLED:

        error = RuntimeError(
            "Local translation provider is disabled."
        )

        return (
            translations,
            [error for _ in range(item_count)],
        )

    if not _is_provider_available(
        "local"
    ):

        error = RuntimeError(
            "Local translation provider is in cooldown."
        )

        return (
            translations,
            [error for _ in range(item_count)],
        )

    if not item_count:

        return (
            translations,
            errors,
        )

    try:

        if not is_local_translation_available():

            error = RuntimeError(
                "Local NLLB translation model is unavailable."
            )

            _mark_provider_failure(
                "local"
            )

            return (
                translations,
                [error for _ in range(item_count)],
            )

    except Exception as error:

        _mark_provider_failure(
            "local"
        )

        return (
            translations,
            [error for _ in range(item_count)],
        )

    resolved_sources = [
        ""
        for _ in range(item_count)
    ]

    batch_texts = []
    batch_sources = []
    batch_indices = []

    for index, text in enumerate(texts):

        if not text:

            continue

        try:

            source_code = _resolve_source_language(
                text,
                sources[index],
            )

        except Exception as error:

            # This is an item-level problem.
            # Do not affect the provider health state.
            errors[index] = error

            logger.warning(
                MODULE,
                (
                    "Local NLLB skipped item "
                    f"{index + 1}: {error}"
                ),
            )

            continue

        if source_code not in _LOCAL_LANGUAGE_CODES:

            error = RuntimeError(
                (
                    "Local NLLB does not currently "
                    f"support source language '{source_code}'."
                )
            )

            errors[index] = error

            logger.warning(
                MODULE,
                (
                    "Local NLLB skipped item "
                    f"{index + 1}: unsupported source "
                    f"language '{source_code}'."
                ),
            )

            continue

        resolved_sources[index] = source_code

        batch_texts.append(
            text
        )

        batch_sources.append(
            source_code
        )

        batch_indices.append(
            index
        )

    if not batch_texts:

        return (
            translations,
            errors,
        )

    target_code = _normalize_language_code(
        target
    )

    if not target_code:

        error = RuntimeError(
            "Target language is not configured."
        )

        return (
            translations,
            [
                error if texts[index] else None
                for index in range(item_count)
            ],
        )

    logger.info(
        MODULE,
        (
            "Local NLLB batch started for "
            f"{len(batch_texts)} item(s), "
            "using one mixed-language batch."
        ),
    )

    batch_start = time.perf_counter()

    try:

        batch_results = local_translate_text_batch(
            batch_texts,
            batch_sources,
            target_code,
        )

    except Exception as error:

        elapsed = (
            time.perf_counter()
            - batch_start
        )

        logger.error(
            MODULE,
            (
                "Local NLLB batch failed after "
                f"{elapsed:.3f} seconds: {error}"
            ),
        )

        _mark_provider_failure(
            "local"
        )

        for index in batch_indices:

            errors[index] = error

        return (
            translations,
            errors,
        )

    elapsed = (
        time.perf_counter()
        - batch_start
    )

    if (
        not isinstance(
            batch_results,
            (list, tuple),
        )
        or len(batch_results) != len(batch_texts)
    ):

        error = RuntimeError(
            "Local NLLB returned an invalid batch result."
        )

        _mark_provider_failure(
            "local"
        )

        for index in batch_indices:

            errors[index] = error

        return (
            translations,
            errors,
        )

    successful_count = 0

    for index, translated_text in zip(
        batch_indices,
        batch_results,
    ):

        if _is_invalid_translation_response(
            translated_text
        ):

            errors[index] = RuntimeError(
                "Local NLLB returned an invalid translation."
            )

            continue

        translated_text = str(
            translated_text
        ).strip()

        if not translated_text:

            errors[index] = RuntimeError(
                "Local NLLB returned an empty translation."
            )

            continue

        translations[index] = (
            translated_text
        )

        successful_count += 1

    if successful_count:

        _mark_provider_success(
            "local"
        )

    logger.info(
        MODULE,
        (
            "Local NLLB batch completed: "
            f"{successful_count}/{len(batch_texts)} "
            f"item(s) in {elapsed:.3f} seconds."
        ),
    )

    return (
        translations,
        errors,
    )


# --------------------------------------------------
# MyMemory provider
# --------------------------------------------------


def _translate_with_mymemory(
    text,
    source,
    target,
):
    """
    Translate text using the MyMemory REST API.

    When source is "auto", the source language is detected
    locally before the MyMemory request.

    Returns
    -------
    tuple
        (translated_text, error)
    """
    if not _is_provider_available(
        "mymemory"
    ):

        return (
            None,
            RuntimeError(
                "MyMemory provider is in cooldown."
            ),
        )

    try:

        source_code = _resolve_source_language(
            text,
            source,
        )

        target_code = _normalize_language_code(
            target
        )

    except Exception as error:

        return (
            None,
            error,
        )

    if not source_code:

        return (
            None,
            RuntimeError(
                "Source language is not configured."
            ),
        )

    if not target_code:

        return (
            None,
            RuntimeError(
                "Target language is not configured."
            ),
        )

    try:

        session = _get_mymemory_session()

        response = session.get(
            MYMEMORY_BASE_URL,
            params={
                "q": text,
                "langpair": (
                    f"{source_code}|{target_code}"
                ),
            },
            timeout=MYMEMORY_TIMEOUT,
        )

        status_code = response.status_code

        if status_code == 429:

            error = RuntimeError(
                "MyMemory returned HTTP 429 "
                "(rate limited)."
            )

            _mark_provider_failure(
                "mymemory"
            )

            return (
                None,
                error,
            )

        if status_code >= 500:

            error = RuntimeError(
                (
                    "MyMemory returned server error "
                    f"HTTP {status_code}."
                )
            )

            _mark_provider_failure(
                "mymemory"
            )

            return (
                None,
                error,
            )

        response.raise_for_status()

        payload = response.json()

        response_status = payload.get(
            "responseStatus"
        )

        if response_status != 200:

            error = RuntimeError(
                (
                    "MyMemory returned response status "
                    f"{response_status}."
                )
            )

            _mark_provider_failure(
                "mymemory"
            )

            return (
                None,
                error,
            )

        response_data = payload.get(
            "responseData"
        )

        if not isinstance(
            response_data,
            dict,
        ):

            return (
                None,
                RuntimeError(
                    "MyMemory returned an invalid response."
                ),
            )

        translated_text = response_data.get(
            "translatedText"
        )

        if _is_invalid_translation_response(
            translated_text
        ):

            return (
                None,
                RuntimeError(
                    "MyMemory returned an invalid translation."
                ),
            )

        translated_text = str(
            translated_text
        ).strip()

        _mark_provider_success(
            "mymemory"
        )

        return (
            translated_text,
            None,
        )

    except requests.Timeout:

        _mark_provider_failure(
            "mymemory"
        )

        return (
            None,
            TimeoutError(
                "MyMemory request timed out."
            ),
        )

    except requests.RequestException as error:

        _mark_provider_failure(
            "mymemory"
        )

        return (
            None,
            error,
        )

    except Exception as error:

        _mark_provider_failure(
            "mymemory"
        )

        return (
            None,
            error,
        )


# --------------------------------------------------
# Google provider
# --------------------------------------------------


def _translate_with_google(
    text,
    source,
    target,
):
    """
    Translate text using GoogleTranslator.

    This provider is retained as a fallback so the translation
    architecture can support multiple providers.

    Google is not the primary provider.
    """
    if not GOOGLE_PROVIDER_ENABLED:

        return (
            None,
            RuntimeError(
                "Google provider is disabled."
            ),
        )

    if not _is_provider_available(
        "google"
    ):

        return (
            None,
            RuntimeError(
                "Google provider is in cooldown."
            ),
        )

    try:

        source_code = _resolve_source_language(
            text,
            source,
        )

        target_code = _normalize_language_code(
            target
        )

        if not source_code:

            return (
                None,
                RuntimeError(
                    "Source language is not configured."
                ),
            )

        if not target_code:

            return (
                None,
                RuntimeError(
                    "Target language is not configured."
                ),
            )

        translator = _get_translator(
            source_code,
            target_code,
        )

        translated_text = translator.translate(
            text
        )

        if _is_invalid_translation_response(
            translated_text
        ):

            error = RuntimeError(
                "Google returned an invalid translation."
            )

            _mark_provider_failure(
                "google"
            )

            return (
                None,
                error,
            )

        translated_text = str(
            translated_text
        ).strip()

        _mark_provider_success(
            "google"
        )

        return (
            translated_text,
            None,
        )

    except Exception as error:

        _mark_provider_failure(
            "google"
        )

        return (
            None,
            error,
        )


# --------------------------------------------------
# Provider selection
# --------------------------------------------------


def _perform_translation(
    text,
    source,
    target,
):
    """
    Try available translation providers in priority order.

    Priority:
        1. Local NLLB
        2. MyMemory
        3. Google

    Returns
    -------
    tuple
        (translated_text, error)
    """
    providers = []

    if LOCAL_PROVIDER_ENABLED:

        providers.append(
            (
                "local",
                _translate_with_local,
            )
        )

    providers.append(
        (
            "mymemory",
            _translate_with_mymemory,
        )
    )

    if GOOGLE_PROVIDER_ENABLED:

        providers.append(
            (
                "google",
                _translate_with_google,
            )
        )

    last_error = None

    for provider_name, provider_function in providers:

        if not _is_provider_available(
            provider_name
        ):

            logger.info(
                MODULE,
                (
                    f"Skipping translation provider "
                    f"'{provider_name}' because it is "
                    "currently in cooldown."
                ),
            )

            continue

        logger.info(
            MODULE,
            (
                "Translation provider attempt: "
                f"{provider_name}."
            ),
        )

        translated_text, error = (
            provider_function(
                text,
                source,
                target,
            )
        )

        if error is None:

            logger.info(
                MODULE,
                (
                    "Translation provider succeeded: "
                    f"{provider_name}."
                ),
            )

            return (
                translated_text,
                None,
            )

        last_error = error

        logger.warning(
            MODULE,
            (
                f"Translation provider "
                f"'{provider_name}' failed: "
                f"{error}"
            ),
        )

    if last_error is None:

        last_error = RuntimeError(
            "No translation provider is currently available."
        )

    return (
        None,
        last_error,
    )


# --------------------------------------------------
# Core translation
# --------------------------------------------------


def _translate_text_unlocked(
    text,
    source=DEFAULT_SOURCE_LANGUAGE,
    target=DEFAULT_TARGET_LANGUAGE,
):
    """
    Translate one text without acquiring the cache lock.

    Handles:
        - cache lookup
        - automatic source detection
        - provider selection
        - limited retry
        - provider cooldown
        - successful-result caching
    """
    if not text or not text.strip():
        return ""

    text = text.strip()

    if (
        source
        and target
        and isinstance(source, str)
        and source.lower() == target.lower()
    ):
        return text

    cache_found, cached_translation = (
        _get_cached_translation(
            text,
            source,
            target,
        )
    )

    if cache_found:

        logger.info(
            MODULE,
            (
                "Translation cache hit "
                f"({len(text)} characters)."
            ),
        )

        return cached_translation

    for attempt in range(
        1,
        TRANSLATION_RETRIES + 1,
    ):

        translated_text, error = (
            _perform_translation(
                text,
                source,
                target,
            )
        )

        if error is None:

            translated_text = str(
                translated_text
            ).strip()

            if translated_text:

                _store_cached_translation(
                    text,
                    source,
                    target,
                    translated_text,
                )

                return translated_text

        else:

            logger.error(
                MODULE,
                (
                    f"Translation failed on attempt "
                    f"{attempt}: {error}"
                ),
            )

        if attempt < TRANSLATION_RETRIES:

            time.sleep(
                TRANSLATION_RETRY_DELAY
            )

    return ""


# --------------------------------------------------
# Public single-text API
# --------------------------------------------------


def translate_text(
    text,
    source=DEFAULT_SOURCE_LANGUAGE,
    target=DEFAULT_TARGET_LANGUAGE,
):
    """
    Translate one text.

    Same source/target returns original text.

    Empty or unresolved translation returns "".
    """
    if not text or not text.strip():
        return ""

    text = text.strip()

    if (
        source
        and target
        and isinstance(source, str)
        and source.lower() == target.lower()
    ):
        return text

    logger.info(
        MODULE,
        (
            "Translation started "
            f"({len(text)} characters)."
        ),
    )

    cache_found, cached_translation = (
        _get_cached_translation(
            text,
            source,
            target,
        )
    )

    if cache_found:

        logger.info(
            MODULE,
            (
                "Translation cache hit "
                f"({len(text)} characters)."
            ),
        )

        return cached_translation

    translated_text = _translate_text_unlocked(
        text,
        source,
        target,
    )

    if translated_text:

        logger.info(
            MODULE,
            (
                "Translation completed "
                f"({len(text)} characters)."
            ),
        )

    else:

        logger.warning(
            MODULE,
            (
                "Translation unresolved. "
                "Existing cached translations remain "
                "unchanged."
            ),
        )

    return translated_text


# --------------------------------------------------
# Batch worker
# --------------------------------------------------


def _translate_batch_item(args):
    """
    Worker function used for individual fallback/recovery.

    The tuple contains:
        text
        source
        target
    """
    text, source, target = args

    if not text:
        return ""

    return _translate_text_unlocked(
        text,
        source,
        target,
    )


# --------------------------------------------------
# Batch recovery helpers
# --------------------------------------------------


def _get_failed_batch_indices(
    original_texts,
    translated_texts,
):
    """
    Return indexes for non-empty source texts that did not
    receive a valid translation.
    """
    failed_indices = []

    for index, original_text in enumerate(
        original_texts
    ):

        translated_text = (
            translated_texts[index]
        )

        if not original_text:
            continue

        if not translated_text:

            failed_indices.append(
                index
            )

    return failed_indices


def _retry_failed_batch_items(
    normalized_texts,
    translated_texts,
    batch_sources,
    target,
):
    """
    Retry only failed batch items using controlled recovery.

    Successful translations are never submitted again.

    Recovery is intentionally per-item because the primary local
    NLLB batch has already been attempted.
    """
    failed_indices = _get_failed_batch_indices(
        normalized_texts,
        translated_texts,
    )

    if not failed_indices:

        return translated_texts

    logger.warning(
        MODULE,
        (
            "Batch translation detected "
            f"{len(failed_indices)} failed item(s). "
            "Starting controlled recovery."
        ),
    )

    for recovery_attempt in range(
        1,
        TRANSLATION_BATCH_RECOVERY_RETRIES + 1,
    ):

        if recovery_attempt > 1:

            time.sleep(
                TRANSLATION_BATCH_RECOVERY_DELAY
            )

        logger.info(
            MODULE,
            (
                "Translation recovery pass "
                f"{recovery_attempt}/"
                f"{TRANSLATION_BATCH_RECOVERY_RETRIES} "
                "starting for "
                f"{len(failed_indices)} item(s)."
            ),
        )

        recovery_arguments = [
            (
                normalized_texts[index],
                batch_sources[index],
                target,
            )
            for index in failed_indices
        ]

        try:

            with ThreadPoolExecutor(
                max_workers=1,
                thread_name_prefix="TranslationRecovery",
            ) as executor:

                recovery_results = list(
                    executor.map(
                        _translate_batch_item,
                        recovery_arguments,
                    )
                )

        except Exception as error:

            logger.error(
                MODULE,
                (
                    "Translation recovery pass "
                    f"{recovery_attempt} failed: "
                    f"{error}"
                ),
            )

            continue

        recovered_count = 0

        for index, translated_text in zip(
            failed_indices,
            recovery_results,
        ):

            if translated_text:

                translated_texts[index] = (
                    translated_text
                )

                recovered_count += 1

        logger.info(
            MODULE,
            (
                "Translation recovery pass "
                f"{recovery_attempt} completed: "
                f"{recovered_count}/"
                f"{len(failed_indices)} item(s) recovered."
            ),
        )

        failed_indices = _get_failed_batch_indices(
            normalized_texts,
            translated_texts,
        )

        if not failed_indices:

            logger.info(
                MODULE,
                "Translation recovery completed successfully.",
            )

            break

    if failed_indices:

        logger.error(
            MODULE,
            (
                "Translation recovery exhausted with "
                f"{len(failed_indices)} unresolved "
                "item(s)."
            ),
        )

    return translated_texts


# --------------------------------------------------
# Public batch API
# --------------------------------------------------


def translate_text_batch(
    texts,
    source=DEFAULT_SOURCE_LANGUAGE,
    target=DEFAULT_TARGET_LANGUAGE,
):
    """
    Translate multiple text blocks.

    Local NLLB is attempted as ONE true mixed-language batch.

    Parameters
    ----------
    texts : sequence
        Text blocks to translate.

    source : str or sequence
        Either one source language applied to every text,
        or one source language per text block.

        Examples:
            source="ja"

            source=["ja", "ja", "hi", "hi"]

    target : str
        Target language applied to every text block.

    Features:
        - local NLLB translation as primary provider
        - true mixed-language NLLB batching
        - Unicode-script language detection
        - translation cache
        - automatic source detection
        - provider fallback
        - provider cooldown
        - limited retries
        - controlled external-provider concurrency
        - failed-item recovery
        - successful-result preservation
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

    total_items = len(
        normalized_texts
    )

    try:

        batch_sources = _expand_batch_sources(
            source,
            total_items,
        )

    except ValueError as error:

        logger.error(
            MODULE,
            f"Invalid batch source configuration: {error}",
        )

        return [
            ""
            for _ in normalized_texts
        ]

    normalized_target = _normalize_language_code(
        target
    )

    if not normalized_target:

        logger.error(
            MODULE,
            "Batch translation target language is not configured.",
        )

        return [
            ""
            for _ in normalized_texts
        ]

    # --------------------------------------------------
    # Prepare result array.
    # --------------------------------------------------

    translated_texts = [
        ""
        for _ in normalized_texts
    ]

    # --------------------------------------------------
    # Resolve same-language items and cache hits first.
    # --------------------------------------------------

    translation_indices = []

    cache_hits = 0

    for index, text in enumerate(
        normalized_texts
    ):

        item_source = batch_sources[index]

        if not text:
            continue

        # Explicit source == target.
        if (
            isinstance(
                item_source,
                str,
            )
            and item_source
            and item_source.lower()
            == normalized_target.lower()
        ):

            translated_texts[index] = text
            continue

        cache_found, cached_translation = (
            _get_cached_translation(
                text,
                item_source,
                target,
            )
        )

        if cache_found:

            translated_texts[index] = (
                cached_translation
            )

            cache_hits += 1
            continue

        translation_indices.append(
            index
        )

    if cache_hits:

        logger.info(
            MODULE,
            (
                "Batch translation cache contains "
                f"{cache_hits}/{total_items} item(s)."
            ),
        )

    if not translation_indices:

        logger.info(
            MODULE,
            (
                "Batch translation completed entirely "
                "from cache or same-language optimization."
            ),
        )

        return translated_texts

    logger.info(
        MODULE,
        (
            "Batch translation started for "
            f"{total_items} text block(s) using "
            "local NLLB as the primary provider."
        ),
    )

    start_time = time.perf_counter()

    # --------------------------------------------------
    # PRIMARY PROVIDER: ONE NLLB BATCH
    # --------------------------------------------------

    local_texts = [
        normalized_texts[index]
        for index in translation_indices
    ]

    local_sources = [
        batch_sources[index]
        for index in translation_indices
    ]

    local_translations, local_errors = (
        _translate_with_local_batch(
            local_texts,
            local_sources,
            target,
        )
    )

    local_success_count = 0

    fallback_indices = []

    for local_position, original_index in enumerate(
        translation_indices
    ):

        translated_text = (
            local_translations[local_position]
        )

        if translated_text:

            translated_texts[original_index] = (
                translated_text
            )

            _store_cached_translation(
                normalized_texts[original_index],
                local_sources[local_position],
                target,
                translated_text,
            )

            local_success_count += 1

        else:

            fallback_indices.append(
                original_index
            )

    logger.info(
        MODULE,
        (
            "Local NLLB primary batch result: "
            f"{local_success_count}/"
            f"{len(translation_indices)} item(s) translated."
        ),
    )

    # --------------------------------------------------
    # FALLBACK PROVIDERS
    # --------------------------------------------------
    #
    # Only unresolved items reach this stage.
    #
    # This keeps successful local NLLB translations untouched.
    # --------------------------------------------------

    if fallback_indices:

        logger.warning(
            MODULE,
            (
                "Local NLLB left "
                f"{len(fallback_indices)} item(s) unresolved. "
                "Starting fallback providers."
            ),
        )

        fallback_arguments = [
            (
                normalized_texts[index],
                batch_sources[index],
                target,
            )
            for index in fallback_indices
        ]

        try:

            with ThreadPoolExecutor(
                max_workers=TRANSLATION_MAX_WORKERS,
                thread_name_prefix="TranslationFallback",
            ) as executor:

                fallback_results = list(
                    executor.map(
                        _translate_batch_item,
                        fallback_arguments,
                    )
                )

        except Exception as error:

            logger.error(
                MODULE,
                f"Translation fallback failed: {error}",
            )

            fallback_results = [
                ""
                for _ in fallback_indices
            ]

        fallback_success_count = 0

        for index, translated_text in zip(
            fallback_indices,
            fallback_results,
        ):

            if translated_text:

                translated_texts[index] = (
                    translated_text
                )

                _store_cached_translation(
                    normalized_texts[index],
                    batch_sources[index],
                    target,
                    translated_text,
                )

                fallback_success_count += 1

        logger.info(
            MODULE,
            (
                "Fallback translation completed: "
                f"{fallback_success_count}/"
                f"{len(fallback_indices)} item(s) recovered."
            ),
        )

    # --------------------------------------------------
    # Final controlled recovery
    # --------------------------------------------------

    translated_texts = (
        _retry_failed_batch_items(
            normalized_texts,
            translated_texts,
            batch_sources,
            target,
        )
    )

    elapsed = (
        time.perf_counter()
        - start_time
    )

    successful_count = sum(
        1
        for original, translated in zip(
            normalized_texts,
            translated_texts,
        )
        if not original or translated
    )

    unresolved_count = sum(
        1
        for original, translated in zip(
            normalized_texts,
            translated_texts,
        )
        if original and not translated
    )

    logger.info(
        MODULE,
        (
            "Batch translation completed: "
            f"{successful_count}/{total_items} item(s) "
            f"in {elapsed:.3f} seconds."
        ),
    )

    if unresolved_count:

        logger.warning(
            MODULE,
            (
                "Batch translation finished with "
                f"{unresolved_count} unresolved item(s). "
                "Existing successful translations were preserved."
            ),
        )

    return translated_texts