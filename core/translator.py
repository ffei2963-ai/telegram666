"""翻译服务 - Google Translate 集成"""

import re
from utils.logger import setup_logger

logger = setup_logger(__name__)


class Translator:

    def __init__(self):
        self._translator = None

    def _get_translator(self):
        if self._translator:
            return self._translator
        try:
            from deep_translator import GoogleTranslator
            self._translator = GoogleTranslator
            return self._translator
        except ImportError:
            logger.warning("deep_translator 未安装，翻译功能将受限")
            return None

    def _detect_lang(self, text: str) -> str:
        has_chinese = bool(re.search(r'[\u4e00-\u9fff]', text))
        if has_chinese:
            return "zh"
        has_japanese = bool(re.search(r'[\u3040-\u309f\u30a0-\u30ff]', text))
        has_korean = bool(re.search(r'[\uac00-\ud7af]', text))
        has_cyrillic = bool(re.search(r'[\u0400-\u04ff]', text))
        has_arabic = bool(re.search(r'[\u0600-\u06ff]', text))
        has_thai = bool(re.search(r'[\u0e00-\u0e7f]', text))

        if has_japanese:
            return "ja"
        if has_korean:
            return "ko"
        if has_cyrillic:
            return "ru"
        if has_arabic:
            return "ar"
        if has_thai:
            return "th"
        return "en"

    def to_chinese(self, text: str) -> str:
        if not text or not text.strip():
            return ""

        if self._detect_lang(text) == "zh":
            return text

        GT = self._get_translator()
        if GT is None:
            return f"[翻译未启用] {text[:100]}"

        try:
            translated = GT(source="auto", target="zh-CN").translate(text[:1000])
            return translated
        except Exception as e:
            logger.error("翻译失败: %s", e)
            return f"[翻译失败] {text[:100]}"

    def from_chinese(self, text: str, target_lang: str = "en") -> str:
        if not text or not text.strip():
            return ""

        if self._detect_lang(text) != "zh":
            return text

        GT = self._get_translator()
        if GT is None:
            return f"[Translation unavailable] {text[:100]}"

        try:
            translated = GT(source="zh-CN", target=target_lang).translate(text[:1000])
            return translated
        except Exception as e:
            logger.error("翻译失败: %s", e)
            return f"[Translation failed] {text[:100]}"

    def to_english(self, text: str) -> str:
        return self.from_chinese(text, "en")


_default_translator = None


def get_translator() -> Translator:
    global _default_translator
    if _default_translator is None:
        _default_translator = Translator()
    return _default_translator
