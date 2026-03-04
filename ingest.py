import argparse
import json
import re
from pathlib import Path
from typing import Dict, Iterable, List

import requests

from matcher import SageMatcher, build_alias_rows, normalize_hebrew, strip_html
from talmud_db import DB_PATH, connect, init_db, insert_statements, replace_sages
from tractates import TRACTATE_MAX_DAF, daf_range

SEFARIA_BASE = "https://www.sefaria.org"
SAGES_PATH = Path("data/sages.json")

NAMED_ENTITY_RE = re.compile(
    r'<a[^>]*class="[^"]*namedEntityLink[^"]*"[^>]*data-slug="([^"]+)"[^>]*>(.*?)</a>',
    re.IGNORECASE | re.DOTALL,
)
GEN_RE = re.compile(r"^(T|A|TA|Z|KG)")
GENERIC_SLUGS = {"rav", "rabi"}
GENERIC_HE_NAMES = {"רבי", "רב", "רב (שם אמורא)"}


def load_sages() -> List[Dict]:
    payload = json.loads(SAGES_PATH.read_text(encoding="utf-8"))
    items = payload.get("items") or []
    return [s for s in items if str(s.get("name", "")).strip()]


def fetch_daf_v3(tractate: str, daf: str, timeout: int = 30) -> Dict:
    ref = f"{tractate}.{daf}"
    url = f"{SEFARIA_BASE}/api/v3/texts/{ref}"
    params = {
        "version": "primary",
        "fill_in_missing_segments": 1,
        "return_format": "wrap_all_entities",
    }
    resp = requests.get(url, params=params, timeout=timeout)
    resp.raise_for_status()
    data = resp.json()
    versions = data.get("versions") or []
    segments = []
    if versions:
        segments = versions[0].get("text") or []
    return {"segments": segments}


def fetch_topic(slug: str, timeout: int = 30) -> Dict:
    url = f"{SEFARIA_BASE}/api/topics/{slug}"
    resp = requests.get(url, timeout=timeout)
    resp.raise_for_status()
    return resp.json()


def fetch_talmudic_figure_slugs(timeout: int = 60) -> set[str]:
    url = f"{SEFARIA_BASE}/api/topics/talmudic-figures"
    resp = requests.get(url, params={"with_links": 1}, timeout=timeout)
    resp.raise_for_status()
    payload = resp.json()
    links = (payload.get("links") or {}).get("displays-above") or {}
    out: set[str] = set()
    for row in links.get("links") or []:
        slug = str(row.get("topic") or "").strip()
        if slug:
            out.add(slug)
    if not out:
        raise RuntimeError("No talmudic-figures slugs returned by Sefaria.")
    return out


def extract_named_entities(segment_html: str) -> List[Dict]:
    entities = []
    for slug, html_text in NAMED_ENTITY_RE.findall(segment_html or ""):
        mention_text = strip_html(html_text).strip()
        if not slug or not mention_text:
            continue
        entities.append({"slug": slug.strip(), "text": mention_text})
    return entities


def resolve_person_mentions(
    entities: List[Dict],
    topic_cache: Dict[str, Dict],
    discovered_people: Dict[str, Dict],
    talmudic_slugs: set[str],
    allow_ambiguous: bool,
) -> List[Dict]:
    mentions: List[Dict] = []
    for ent in entities:
        raw_slug = ent["slug"]
        topic = topic_cache.get(raw_slug)
        if topic is None:
            try:
                topic = fetch_topic(raw_slug)
            except Exception:  # noqa: BLE001
                topic = {}
            topic_cache[raw_slug] = topic

        resolved_people = []
        if str(topic.get("subclass") or "").lower() == "person":
            if raw_slug in talmudic_slugs:
                resolved_people = [topic]
        elif topic.get("isAmbiguous"):
            possibilities = [
                p
                for p in (topic.get("possibilities") or [])
                if str(p.get("subclass") or "").lower() == "person"
                and str(p.get("slug") or "").strip() in talmudic_slugs
            ]
            if allow_ambiguous and len(possibilities) == 1:
                resolved_people = [possibilities[0]]

        for person in resolved_people:
            slug = str(person.get("slug") or "").strip()
            if not slug:
                continue
            primary = person.get("primaryTitle") or {}
            name = _pick_display_name(person, ent["text"])
            generation = str((person.get("properties") or {}).get("generation", {}).get("value", "")).strip()
            if not _is_likely_talmudic_sage(slug, name, str(primary.get("en") or ""), generation):
                continue

            aliases = set()
            aliases.add(name)
            for t in person.get("titles") or []:
                txt = str(t.get("text") or "").strip()
                if txt:
                    aliases.add(txt)

            discovered = discovered_people.setdefault(
                slug,
                {
                    "slug": slug,
                    "name": name,
                    "aliases": set(),
                    "generation": generation,
                    "yeshiva": "",
                },
            )
            discovered["aliases"].update(aliases)

            mentions.append({"sage_slug": slug, "match": ent["text"]})

    unique = {(m["sage_slug"], m["match"]): m for m in mentions}
    return list(unique.values())


def _is_likely_talmudic_sage(slug: str, he_name: str, en_name: str, generation: str) -> bool:
    s = slug.lower()
    he = (he_name or "").strip()
    en = (en_name or "").strip().lower()
    gen = (generation or "").strip().upper()

    if s in GENERIC_SLUGS or he in GENERIC_HE_NAMES:
        return False
    if gen and GEN_RE.match(gen):
        return True
    if s.startswith(("rabbi-", "rav-", "rabban-", "rebbi-", "rabi-")):
        return True
    if he.startswith(("רבי", "רב ", "רבן", 'ר"', "ר״")):
        return True
    if any(token in en for token in ("rabbi", "rav", "rabban", "rebbi")):
        return True
    return False


def _pick_display_name(person: Dict, fallback: str) -> str:
    titles = person.get("titles") or []
    candidates = [str(t.get("text") or "").strip() for t in titles if str(t.get("lang") or "") == "he" and str(t.get("text") or "").strip()]
    if not candidates:
        primary = person.get("primaryTitle") or {}
        return str(primary.get("he") or primary.get("en") or fallback).strip()

    def score(txt: str) -> tuple[int, int]:
        s = 0
        if txt.startswith(("רבי ", "רב ", "רבן ", "ר׳", "ר\"")):
            s += 4
        if txt.startswith("ר "):
            s -= 3
        if "[" in txt or "(" in txt:
            s -= 2
        return (s, len(txt))

    return max(candidates, key=score)


def iter_statement_candidates(
    tractate: str,
    max_daf: int,
    mode: str,
    matcher: SageMatcher,
    topic_cache: Dict[str, Dict],
    discovered_people: Dict[str, Dict],
    talmudic_slugs: set[str],
    allow_ambiguous: bool,
) -> Iterable[Dict]:
    for daf in daf_range(max_daf):
        try:
            payload = fetch_daf_v3(tractate, daf)
        except Exception as exc:  # noqa: BLE001
            print(f"skip {tractate}.{daf}: {exc}")
            continue

        segments = payload.get("segments") or []
        for idx, raw_html in enumerate(segments, start=1):
            text_he = strip_html(str(raw_html or "")).strip()
            if not text_he:
                continue

            mentions = []
            if mode in {"sefaria", "hybrid"}:
                entities = extract_named_entities(str(raw_html or ""))
                mentions = resolve_person_mentions(
                    entities=entities,
                    topic_cache=topic_cache,
                    discovered_people=discovered_people,
                    talmudic_slugs=talmudic_slugs,
                    allow_ambiguous=allow_ambiguous,
                )

            if not mentions and mode in {"heuristic", "hybrid"}:
                heuristic = matcher.find_mentions(text_he)
                mentions = [{"sage_slug": f"heuristic:{m['sage_id']}", "match": m["match"]} for m in heuristic]

            if not mentions:
                continue

            yield {
                "tractate": tractate,
                "daf": daf,
                "segment": idx,
                "text_he": text_he,
                "text_he_normalized": normalize_hebrew(text_he),
                "mentions": mentions,
            }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build searchable talmud statements DB by sage.")
    parser.add_argument(
        "--tractates",
        nargs="+",
        default=["Berakhot"],
        help="Tractates to ingest (default: Berakhot).",
    )
    parser.add_argument(
        "--db",
        default=str(DB_PATH),
        help="Path to sqlite database (default: data/talmud.sqlite3)",
    )
    parser.add_argument(
        "--mode",
        choices=["sefaria", "heuristic", "hybrid"],
        default="hybrid",
        help="Identification source: sefaria, heuristic, or hybrid (recommended).",
    )
    parser.add_argument(
        "--max-daf-number",
        type=int,
        default=None,
        help="Optional cap for testing (e.g. 5 ingests through 5b).",
    )
    parser.add_argument(
        "--allow-ambiguous",
        action="store_true",
        help="Include ambiguous named entities only when they resolve to exactly one person possibility.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    selected = []
    for tractate in args.tractates:
        if tractate not in TRACTATE_MAX_DAF:
            raise SystemExit(f"Unknown tractate: {tractate}")
        selected.append(tractate)

    seed_sages = load_sages()
    seed_alias_objects = build_alias_rows(seed_sages)
    matcher = SageMatcher(seed_alias_objects)

    db_path = Path(args.db)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = connect(db_path)
    init_db(conn)

    topic_cache: Dict[str, Dict] = {}
    discovered_people: Dict[str, Dict] = {}
    statements_buffer: List[Dict] = []
    talmudic_slugs = fetch_talmudic_figure_slugs() if args.mode in {"sefaria", "hybrid"} else set()

    for tractate in selected:
        max_daf = TRACTATE_MAX_DAF[tractate]
        if args.max_daf_number is not None:
            max_daf = min(max_daf, max(2, int(args.max_daf_number)))
        print(f"Ingesting {tractate} (2a..{max_daf}b)")
        tractate_rows = list(
            iter_statement_candidates(
                tractate=tractate,
                max_daf=max_daf,
                mode=args.mode,
                matcher=matcher,
                topic_cache=topic_cache,
                discovered_people=discovered_people,
                talmudic_slugs=talmudic_slugs,
                allow_ambiguous=args.allow_ambiguous,
            )
        )
        statements_buffer.extend(tractate_rows)
        print(f"{tractate}: collected {len(tractate_rows)} statements")

    # Canonical sage set is always the local curated list (former SAGE_INFO).
    sages = seed_sages
    alias_objects = seed_alias_objects
    alias_norm_to_sage_id = {a.alias_normalized: a.sage_id for a in alias_objects}
    slug_to_id = {f"heuristic:{a.sage_id}": a.sage_id for a in alias_objects}

    alias_rows = [
        {"sage_id": a.sage_id, "alias": a.alias, "alias_normalized": a.alias_normalized}
        for a in alias_objects
    ]
    replace_sages(conn, sages, alias_rows)

    normalized_rows = []
    for row in statements_buffer:
        mapped_mentions = []
        for m in row["mentions"]:
            sid = slug_to_id.get(m["sage_slug"])
            if not sid:
                sid = alias_norm_to_sage_id.get(normalize_hebrew(m["match"]))
            if not sid:
                continue
            mapped_mentions.append({"sage_id": sid, "match": m["match"]})
        if not mapped_mentions:
            continue
        normalized_rows.append({**row, "mentions": mapped_mentions})

    inserted = insert_statements(conn, normalized_rows)
    print(f"Done. inserted {inserted} statements; sages in DB: {len(sages)}")


if __name__ == "__main__":
    main()
