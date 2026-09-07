"""
Fast and robust Discord message parser for promo codes.
Optimized for single codes and multi-level drops.
"""
import re
import time
from typing import Optional, List, Tuple
from app.models import ParsedCode

# Pre-compiled regular expressions for speed
CODE_TAG_PATTERN = re.compile(
    r"(?:promo[\s_-]*code|bonus[\s_-]*code|gift[\s_-]*code|free[\s_-]*code|kupon[\s_-]*kodu|"
    r"code|promo|promocode|bonus|gift|free|kupon|kod)[\s:=_-]+([A-Za-z0-9_-]{3,32})",
    re.IGNORECASE,
)

# Multi-level drop parser e.g. "LEVEL 125+\nUse the code VYHUKHER to claim 340 DL"
MULTI_LEVEL_PATTERN = re.compile(
    r"LEVEL\s*(\d+)\+?[^\n]*\n[^\n]*(?:use\s+the\s+code|code)\s+([A-Za-z0-9_-]{3,32})",
    re.IGNORECASE,
)

# Markdown codeblock or backticks: `CODE` or ```CODE```
BACKTICK_PATTERN = re.compile(r"`+([A-Za-z0-9_-]{3,32})`+")

# Direct clean alphanumeric candidate
LINE_CANDIDATE_PATTERN = re.compile(r"^[A-Za-z0-9_-]{3,32}$")

DISCORD_EMOJI_PATTERN = re.compile(r"<a?:[a-zA-Z0-9_]+:[0-9]+>|:[a-zA-Z0-9_]+:")
URL_PATTERN = re.compile(r"https?://\S+")
DISCORD_MENTION_PATTERN = re.compile(r"<@&?[0-9]+>")


class CodeParser:
    """Extracts promo codes from raw Discord messages."""

    @staticmethod
    def clean_text(text: str) -> str:
        """Removes Discord mentions, links, and custom emojis."""
        text = DISCORD_EMOJI_PATTERN.sub(" ", text)
        text = URL_PATTERN.sub(" ", text)
        text = DISCORD_MENTION_PATTERN.sub(" ", text)
        return text

    @classmethod
    def extract_level_codes(cls, content: str) -> List[Tuple[int, str]]:
        """
        Extracts list of (required_level, code) from multi-level announcement messages.
        Works across multiline markdown with bolding, emojis, and spaces.
        Sorts descending by level (highest reward first).
        """
        results = []
        parts = re.split(r"LEVEL\s*(\d+)\+?", content, flags=re.I)
        for i in range(1, len(parts), 2):
            try:
                lvl = int(parts[i])
                chunk = parts[i + 1]
                m_code = re.search(r"(?:use\s+the\s+code|code)\s+\**([A-Za-z0-9_-]{3,32})\**", chunk, re.I)
                if m_code:
                    code_clean = m_code.group(1).strip().upper()
                    if cls.validate_code_format(code_clean):
                        results.append((lvl, code_clean))
            except Exception:
                continue

        # Sort by level descending (e.g. Level 175 first, then 150, 125...)
        results.sort(key=lambda x: x[0], reverse=True)
        return results

    @classmethod
    def extract_raw_code(cls, content: str, user_level: Optional[int] = None) -> Optional[str]:
        """
        Fast extraction heuristic:
        1. Multi-level announcement detection (picks code matching user_level or lowest requirement)
        2. Backticks `CODE` or ```CODE```
        3. Tagged keywords (Code: XYZ)
        4. Line by line evaluation
        """
        if not content:
            return None

        # 1. Check for multi-level announcements
        level_codes = cls.extract_level_codes(content)
        if level_codes:
            if user_level is not None and user_level > 0:
                # Find highest code user is eligible for
                for req_lvl, code in level_codes:
                    if user_level >= req_lvl:
                        return code
            # Fallback: return the code with smallest level requirement (most likely accessible)
            return level_codes[-1][1]

        # 2. Backtick code blocks
        backtick_match = BACKTICK_PATTERN.search(content)
        if backtick_match:
            candidate = backtick_match.group(1).strip()
            if cls.validate_code_format(candidate):
                return candidate.upper()

        cleaned = cls.clean_text(content)

        # 3. Tagged keywords e.g. "🎁 New Code: ABC123XYZ"
        tag_match = CODE_TAG_PATTERN.search(cleaned)
        if tag_match:
            candidate = tag_match.group(1).strip()
            if cls.validate_code_format(candidate):
                return candidate.upper()

        # 4. Line by line evaluation
        lines = [line.strip() for line in cleaned.splitlines() if line.strip()]
        for line in lines:
            cleaned_line = line.strip(" :.-_\"'[](){}")
            if LINE_CANDIDATE_PATTERN.match(cleaned_line):
                if cls.validate_code_format(cleaned_line):
                    return cleaned_line.upper()

        # 5. Standalone single token
        tokens = cleaned.split()
        if len(tokens) == 1:
            candidate = tokens[0].strip(" :.-_\"'[](){}")
            if cls.validate_code_format(candidate):
                return candidate.upper()

        return None

    @staticmethod
    def validate_code_format(code: str) -> bool:
        if not code or len(code) < 3 or len(code) > 32:
            return False
        ignore_words = {
            "HTTP", "HTTPS", "DISCORD", "CHANNEL", "SERVER", "UPDATE",
            "ANNOUNCEMENT", "RULES", "ROLES", "ADMIN", "EVERYONE", "HERE",
            "TRUE", "FALSE", "NONE", "NULL", "GAMBLIT", "GIVEAWAY", "LIMITED"
        }
        if code.upper() in ignore_words:
            return False
        return True

    @classmethod
    def parse_message(
        cls,
        content: str,
        message_id: int,
        channel_id: int,
        guild_id: int,
        author_id: int,
        received_at: Optional[float] = None,
        user_level: Optional[int] = None,
    ) -> Optional[ParsedCode]:
        t0 = received_at or time.time()
        code = cls.extract_raw_code(content, user_level=user_level)
        t1 = time.time()

        if not code:
            return None

        return ParsedCode(
            code=code,
            message_id=message_id,
            channel_id=channel_id,
            guild_id=guild_id,
            author_id=author_id,
            received_at=t0,
            parsed_at=t1,
            raw_content=content,
        )
