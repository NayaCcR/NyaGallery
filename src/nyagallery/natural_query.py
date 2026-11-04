"""Small deterministic natural-language search parser."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
import re

from nyagallery.tags import TagCatalog


@dataclass(frozen=True)
class NaturalQueryPlan:
    query: str
    after: str | None = None
    before: str | None = None
    terms: tuple[str, ...] = ()
    excluded_terms: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, object]:
        return {"query": self.query, "after": self.after, "before": self.before, "terms": list(self.terms), "excluded_terms": list(self.excluded_terms)}


def parse_natural_query(text: str, catalog: TagCatalog, *, today: date | None = None) -> NaturalQueryPlan:
    source = " ".join(text.strip().split())
    current = today or date.today()
    after: str | None = None
    before: str | None = None
    if re.search(r"最近\s*(一周|7\s*天)|last\s+week|past\s+week", source, re.I):
        after = (current - timedelta(days=7)).isoformat()
        before = (current + timedelta(days=1)).isoformat()
        source = re.sub(r"最近\s*(一周|7\s*天)|last\s+week|past\s+week", " ", source, flags=re.I)
    elif re.search(r"最近\s*(一个月|一月|30\s*天)|last\s+month|past\s+month", source, re.I):
        after = (current - timedelta(days=30)).isoformat()
        before = (current + timedelta(days=1)).isoformat()
        source = re.sub(r"最近\s*(一个月|一月|30\s*天)|last\s+month|past\s+month", " ", source, flags=re.I)
    excluded = bool(re.search(r"(R18|R-18|十八禁).{0,4}(除外|排除|exclude|excluded)|\bwithout\s+r18\b", source, re.I))
    if excluded:
        source = re.sub(r"(R18|R-18|十八禁).{0,4}(除外|排除|exclude|excluded)|\bwithout\s+r18\b", " ", source, flags=re.I)
    terms: list[str] = []
    excluded_terms: list[str] = ["rating:r18", "rating:r18g"] if excluded else []
    for raw in re.findall(r"[^\s,，]+", source):
        candidate = raw.strip("\"'()（）")
        if not candidate:
            continue
        negative = candidate.startswith("-")
        candidate = candidate[1:] if negative else candidate
        resolved = catalog.resolve(candidate) or catalog.resolve(candidate.replace("_", " "))
        if resolved:
            (excluded_terms if negative else terms).append(resolved)
    query_parts = [*terms, *(f"-{term}" for term in excluded_terms)]
    return NaturalQueryPlan(query=" ".join(dict.fromkeys(query_parts)), after=after, before=before, terms=tuple(dict.fromkeys(terms)), excluded_terms=tuple(dict.fromkeys(excluded_terms)))
