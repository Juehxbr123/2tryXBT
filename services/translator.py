"""
Переводчик через Google Translate (deep-translator)
"""
import logging
from typing import Optional
import asyncio

logger = logging.getLogger(__name__)


async def translate_to_russian(text: str) -> Optional[str]:
    if not text or len(text.strip()) < 5:
        return None
    try:
        from deep_translator import GoogleTranslator
        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(
            None,
            lambda: GoogleTranslator(source='auto', target='ru').translate(text[:4500])
        )
        if result and result != text:
            return result
        return None
    except Exception as e:
        logger.warning(f"Translation error: {e}")
        return None
