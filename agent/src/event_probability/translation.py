import asyncio
import json
from collections.abc import Awaitable, Callable, Sequence
from typing import Any

from src.providers.chat import ChatLLM
from src.providers.openai_codex import get_event_translation_model

from .models import EventProbability, TranslationStats
from .storage import ProbabilityStorage


TranslateBatch = Callable[[list[str]], Awaitable[dict[str, str]]]
Sleep = Callable[[float], Awaitable[Any]]


def _parse_translation_response(
    content: str | None,
    titles: Sequence[str],
) -> dict[str, str]:
    if not isinstance(content, str):
        return {}

    text = content.strip()
    lines = text.splitlines()
    if (
        len(lines) >= 3
        and lines[0].strip() == "```json"
        and lines[-1].strip() == "```"
    ):
        text = "\n".join(lines[1:-1]).strip()

    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        return {}
    if not isinstance(parsed, dict):
        return {}

    requested = set(titles)
    return {
        key: value
        for key, value in parsed.items()
        if isinstance(key, str)
        and key in requested
        and isinstance(value, str)
    }


class TitleTranslator:
    def __init__(
        self,
        store: ProbabilityStorage,
        *,
        translate_batch: TranslateBatch | None = None,
        sleep: Sleep = asyncio.sleep,
    ) -> None:
        self.store = store
        self.translate_batch = translate_batch or self._default_translate_batch
        self.sleep = sleep

    async def translate(
        self,
        events: Sequence[EventProbability],
        *,
        limit: int,
        batch_size: int = 4,
        batch_delay: float = 1.0,
    ) -> TranslationStats:
        if limit < 0:
            raise ValueError("limit must be non-negative")
        if batch_size < 1:
            raise ValueError("batch_size must be positive")
        if batch_delay < 0:
            raise ValueError("batch_delay must be non-negative")

        cache = self.store.load_translation_cache()
        valid_cache = {
            title: translation
            for title, translation in cache.items()
            if translation.strip()
        }
        targets_by_title: dict[str, list[tuple[Any, str]]] = {}
        for event in events:
            targets_by_title.setdefault(event.question, []).append(
                (event, "question_zh")
            )
            for result in event.results:
                targets_by_title.setdefault(result.label, []).append(
                    (result, "label_zh")
                )

        cache_hits = 0
        new_titles: list[str] = []
        for title, targets in targets_by_title.items():
            cached = valid_cache.get(title)
            if cached:
                cache_hits += 1
                for target, attribute in targets:
                    setattr(target, attribute, cached)
            else:
                new_titles.append(title)

        selected = new_titles[:limit]
        translated_count = 0
        for start in range(0, len(selected), batch_size):
            batch = selected[start : start + batch_size]
            try:
                translated = await self.translate_batch(batch)
            except Exception:
                translated = {}
            if isinstance(translated, dict):
                accepted = {
                    title: value
                    for title, value in translated.items()
                    if title in batch and isinstance(value, str) and value.strip()
                }
                if accepted:
                    cache.update(accepted)
                    valid_cache.update(accepted)
                    try:
                        self.store.save_translation_cache(cache)
                    except OSError:
                        pass
                    translated_count += len(accepted)
                    for title, value in accepted.items():
                        for target, attribute in targets_by_title[title]:
                            setattr(target, attribute, value)
            if start + batch_size < len(selected) and batch_delay:
                await self.sleep(batch_delay)

        pending = sum(
            1
            for title in new_titles
            if title not in valid_cache
        )
        return TranslationStats(
            new_translations=translated_count,
            cache_hits=cache_hits,
            pending=pending,
        )

    @staticmethod
    async def _default_translate_batch(titles: list[str]) -> dict[str, str]:
        prompt = (
            "Translate each exact English prediction-market title into concise "
            "Simplified Chinese. Return only one JSON object whose keys are the "
            "exact input titles and whose values are translations.\n\n"
            f"Titles:\n{json.dumps(titles, ensure_ascii=False)}"
        )

        def call() -> str | None:
            response = ChatLLM(
                model_name=get_event_translation_model(),
                provider="openai-codex",
            ).chat(
                [{"role": "user", "content": prompt}],
                tools=None,
                timeout=45,
            )
            return response.content

        content = await asyncio.to_thread(call)
        if not content:
            return {}
        return _parse_translation_response(content, titles)
