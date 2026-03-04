import re
import unicodedata
from dataclasses import dataclass
from typing import Dict, Iterable, List, Sequence

HEBREW_NIKUD_RE = re.compile(r"[\u0591-\u05C7]")
NON_ALNUM_HE_RE = re.compile(r"[^\w\u0590-\u05FF\s\"׳׳\']+")
MULTISPACE_RE = re.compile(r"\s+")


@dataclass(frozen=True)
class SageAlias:
    sage_id: int
    sage_name: str
    alias: str
    alias_normalized: str


def strip_html(text: str) -> str:
    return re.sub(r"<[^>]+>", "", text or "")


def normalize_hebrew(text: str) -> str:
    text = strip_html(text or "")
    text = unicodedata.normalize("NFKC", text)
    text = HEBREW_NIKUD_RE.sub("", text)
    text = text.replace("־", " ").replace("–", " ").replace("—", " ")
    text = NON_ALNUM_HE_RE.sub(" ", text)
    text = MULTISPACE_RE.sub(" ", text)
    return text.strip().lower()


class SageMatcher:
    def __init__(self, alias_rows: Iterable[SageAlias]):
        self._aliases: List[SageAlias] = sorted(alias_rows, key=lambda a: len(a.alias_normalized), reverse=True)

    def find_mentions(self, raw_text: str) -> List[Dict]:
        text = strip_html(raw_text)
        normalized = normalize_hebrew(text)
        if not normalized:
            return []

        mentions: List[Dict] = []
        for alias in self._aliases:
            pattern = rf"(^|\s)({re.escape(alias.alias_normalized)})(?=\s|$)"
            for m in re.finditer(pattern, normalized):
                mentions.append(
                    {
                        "sage_id": alias.sage_id,
                        "sage_name": alias.sage_name,
                        "alias": alias.alias,
                        "match": m.group(2),
                    }
                )

        # de-duplicate repeated matches in a segment per sage
        unique = {(m["sage_id"], m["match"]): m for m in mentions}
        return list(unique.values())


def build_alias_rows(sages: Sequence[Dict]) -> List[SageAlias]:
    rows: List[SageAlias] = []
    for idx, sage in enumerate(sages, start=1):
        name = str(sage.get("name", "")).strip()
        aliases = list(sage.get("aliases") or [])
        if name and name not in aliases:
            aliases.append(name)

        seen = set()
        for alias in aliases:
            alias = str(alias).strip()
            if not alias:
                continue
            norm = normalize_hebrew(alias)
            if not norm or norm in seen:
                continue
            seen.add(norm)
            rows.append(
                SageAlias(
                    sage_id=idx,
                    sage_name=name,
                    alias=alias,
                    alias_normalized=norm,
                )
            )
    return rows
