"""
Pre-flight validation and repair for generated search queries.

Queries here are assembled from templates filled with merchant context, then layered with
peer-scale qualifiers, a segment anchor, a geography clause, a recency year and up to a
dozen incumbent exclusions. Two things go wrong with that:

  * A blank merchant field leaves a literal empty token (`""`), and the query searches for
    nothing. The engine bills the call and returns noise.
  * Enough stacked operators over-constrains the query. Tavily degrades, and DuckDuckGo
    returns nothing at all for long boolean strings.

Both are detectable without spending an API call, so this module checks a query first and
repairs it by shedding its least load-bearing parts — exclusions, then the segment anchor,
then peer qualifiers — keeping the core intent intact. A query that cannot be repaired into
something searchable is reported as unusable so the caller can skip it rather than burn a
request on it.

Deterministic on purpose: this guards the search step, so it must be cheap and predictable.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass

logger = logging.getLogger(__name__)

#: Engines degrade well before their hard limits once boolean operators stack up.
MAX_QUERY_CHARS = 350
#: A single subject ("Toptal") is a legitimate search; zero is not. Only a query that is
#: operators, exclusions and stopwords all the way down has nothing for an engine to match.
MIN_SUBSTANTIVE_TERMS = 1
#: Exclusions are a soft hint only (a deterministic post-filter enforces scale), so they are
#: the first thing dropped when a query is too long.
MAX_EXCLUSIONS = 6

_OPERATORS = {"or", "and", "not"}
#: Words that qualify a search but are never its subject. A query made only of these -- as
#: happens when the merchant's product and category are both blank -- has nothing to search
#: for, however many words long it looks.
_STOPWORDS = {
    "the", "a", "an", "of", "for", "to", "in", "on", "is", "are", "best", "top", "vs",
    "alternative", "alternatives", "competitor", "competitors", "comparison",
    # commercial qualifiers
    "pricing", "price", "prices", "cost", "costs", "rates", "rate", "fees", "fee",
    "retainer", "plans", "tiers", "quote", "msrp", "discount",
    # sentiment / review qualifiers
    "review", "reviews", "complaint", "complaints", "issue", "issues", "problem",
    "problems", "limitation", "limitations", "downside", "frustration",
    # messaging qualifiers
    "tagline", "slogan", "claims",
}

#: Unquoted template artefacts left behind when a merchant field was blank or unknown.
#: Empty quoted tokens are found by scanning quoted strings instead of by pattern: a naive
#: `"\s+"` also matches the gap between two legitimate adjacent phrases, and stripping that
#: silently welds them into one wrong phrase.
_PLACEHOLDER_WORDS = re.compile(
    r'\{\w+\}|\bNone\b|\bnull\b|\bundefined\b|\bNot stated\b|\bn/a\b',
    re.IGNORECASE,
)
_EXCLUSION_RE = re.compile(r'-"[^"]*"|(?<!\S)-\w[\w.&-]*')
_QUOTED_RE = re.compile(r'"[^"]*"')


def _is_blank_quoted(token: str) -> bool:
    """True for a quoted token with nothing but whitespace inside it."""
    return not token[1:-1].strip()


def _has_placeholder(query: str) -> bool:
    if _PLACEHOLDER_WORDS.search(query):
        return True
    return any(_is_blank_quoted(m.group(0)) for m in _QUOTED_RE.finditer(query))


@dataclass(frozen=True)
class QueryValidation:
    """Outcome of validating one query. `query` is the repaired text when `ok` is True."""

    ok: bool
    query: str
    issues: tuple[str, ...] = ()
    repaired: bool = False

    @property
    def summary(self) -> str:
        return "; ".join(self.issues) if self.issues else "ok"


def _substantive_terms(query: str) -> list[str]:
    """Real search terms: operators, exclusions, site: filters and stopwords do not count."""
    without_exclusions = _EXCLUSION_RE.sub(" ", query)
    cleaned = re.sub(r'[()"]', " ", without_exclusions)
    terms = []
    for token in cleaned.split():
        low = token.lower()
        if low.startswith("site:") or low in _OPERATORS or low in _STOPWORDS:
            continue
        if not any(ch.isalnum() for ch in token):
            continue
        if low.isdigit() and len(low) == 4:  # a bare year is a hint, not a subject
            continue
        terms.append(token)
    return terms


def _balance_quotes(query: str) -> str:
    """Drops a trailing unbalanced quote, which makes engines swallow the rest of the query."""
    if query.count('"') % 2 == 0:
        return query
    index = query.rfind('"')
    return (query[:index] + query[index + 1 :]).strip()


def _balance_parens(query: str) -> str:
    opens, closes = query.count("("), query.count(")")
    if opens == closes:
        return query
    if opens > closes:
        return query + ")" * (opens - closes)
    return "(" * (closes - opens) + query


_CONVERSATIONAL_PREFIX_RE = re.compile(
    r"^(i\s+(want|need|am|wish)|we\s+(want|need|are|wish)|how\s+to|looking\s+to|help\s+me|try(ing)?\s+to|increase|grow|attract)\b",
    re.IGNORECASE,
)


def _strip_placeholders(query: str) -> str:
    """
    Removes unfilled tokens, then collapses the whitespace and dangling operators they
    leave behind. Quoted tokens are removed only when blank, so two adjacent real phrases
    are never merged into one.
    """
    cleaned = _QUOTED_RE.sub(lambda m: " " if _is_blank_quoted(m.group(0)) else m.group(0), query)
    cleaned = _PLACEHOLDER_WORDS.sub(" ", cleaned)
    cleaned = re.sub(r"\(\s*\)", " ", cleaned)
    # An operator left dangling by the removal ("OR OR", a leading/trailing OR).
    cleaned = re.sub(r"\b(OR|AND)\b(\s+\b(OR|AND)\b)+", r"\1", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"^\s*\b(OR|AND)\b\s*|\s*\b(OR|AND)\b\s*$", " ", cleaned, flags=re.IGNORECASE)
    return re.sub(r"\s{2,}", " ", cleaned).strip()


def _unquote_conversational_phrases(query: str) -> str:
    """
    Unquotes conversational goals/sentences trapped inside exact-match quotes
    (e.g., '"i want to increase connections to attract customers"') so exact phrase matching
    does not destroy search engine recall.
    """
    from orchestrator.agents.market_research.intelligence.market_mapping.classification import is_conversational_statement

    def _rep(m: re.Match[str]) -> str:
        token = m.group(0)[1:-1].strip()
        if is_conversational_statement(token):
            words = token.split()
            clean_words = [
                w for w in words
                if w.lower() not in {"i", "want", "to", "my", "we", "our", "me", "us", "more", "how"}
            ]
            return " ".join(clean_words[:4])
        return m.group(0)

    return _QUOTED_RE.sub(_rep, query)


def _trim_exclusions(query: str, keep: int) -> str:
    """Keeps the first `keep` exclusions and drops the rest."""
    seen = 0

    def _replace(match: re.Match[str]) -> str:
        nonlocal seen
        seen += 1
        return match.group(0) if seen <= keep else " "

    return re.sub(r"\s{2,}", " ", _EXCLUSION_RE.sub(_replace, query)).strip()


def _drop_last_quoted_group(query: str) -> str:
    """Sheds the last parenthesised OR-group (segment anchor, then peer qualifiers)."""
    groups = list(re.finditer(r"\([^()]*\bOR\b[^()]*\)", query, flags=re.IGNORECASE))
    if not groups:
        return query
    last = groups[-1]
    return re.sub(r"\s{2,}", " ", query[: last.start()] + query[last.end() :]).strip()


def validate_search_query(query: str) -> QueryValidation:
    """
    Checks a query is searchable and repairs it when it is not.

    Repair order is least-load-bearing first: surplus exclusions, then the trailing OR-groups
    that narrow rather than define the search. The subject terms are never dropped.
    """
    issues: list[str] = []
    original = query or ""
    working = original.strip()

    if not working:
        return QueryValidation(False, "", ("empty query",))

    if _has_placeholder(working):
        issues.append("unfilled placeholder from a blank merchant field")
        working = _strip_placeholders(working)

    if working.count('"') % 2:
        issues.append("unbalanced quote")
        working = _balance_quotes(working)

    if _QUOTED_RE.search(working):
        unquoted = _unquote_conversational_phrases(working)
        if unquoted != working:
            issues.append("unquoted conversational phrase inside exact quotes")
            working = unquoted

    if working.count("(") != working.count(")"):
        issues.append("unbalanced parenthesis")
        working = _balance_parens(working)

    exclusions = _EXCLUSION_RE.findall(working)
    if len(exclusions) > MAX_EXCLUSIONS:
        issues.append(f"{len(exclusions)} exclusions over budget of {MAX_EXCLUSIONS}")
        working = _trim_exclusions(working, MAX_EXCLUSIONS)

    # Shed narrowing groups until the query fits, but never the subject terms.
    guard = 0
    while len(working) > MAX_QUERY_CHARS and guard < 4:
        shortened = _drop_last_quoted_group(working)
        if shortened == working:
            break
        working = shortened
        guard += 1
    if len(working) > MAX_QUERY_CHARS:
        issues.append(f"over {MAX_QUERY_CHARS} chars after trimming")
        working = _trim_exclusions(working, 0)[:MAX_QUERY_CHARS].strip()
        working = _balance_quotes(_balance_parens(working))
    elif guard:
        issues.append("over length; dropped narrowing clauses")

    terms = _substantive_terms(working)
    if len(terms) < MIN_SUBSTANTIVE_TERMS:
        issues.append(
            f"only {len(terms)} substantive term(s); nothing for an engine to match"
        )
        return QueryValidation(False, working, tuple(issues))

    return QueryValidation(
        ok=True,
        query=working,
        issues=tuple(issues),
        repaired=bool(issues) and working != original,
    )
