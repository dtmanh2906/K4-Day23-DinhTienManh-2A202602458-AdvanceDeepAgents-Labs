"""tools.py - STUDENT IMPLEMENTS.  Source tools for the research agents.   Guide: GUIDE.md, part 1.

Rules for every tool:
  * runs on the HOST (not in the sandbox): API keys must never enter the sandbox;
  * returns a STRING (JSON text of compact records) and NEVER raises:
        "NO RESULTS"  when the source answers with nothing,
        "ERROR: ..."  when the source keeps failing after the retries (the agent then tries another source);
  * the docstring is the tool description the LLM reads: keep it precise (what it does, what it returns, when to use it).
Try your tools without any agent:   python tools.py
"""
import json
import os
import random
import re
import time
import xml.etree.ElementTree as ET

import httpx
from langchain_core.tools import tool

# ---- constants (given) ----
ARXIV_URL = "https://export.arxiv.org/api/query"  # https only: http answers 301
HF_DAILY_URL = "https://huggingface.co/api/daily_papers"
HF_SEARCH_URL = "https://huggingface.co/api/papers/search"
EXA_URL = "https://mcp.exa.ai/mcp"

_LAST_ARXIV_CALL = 0.0


def _wait_for_arxiv_politeness():
    global _LAST_ARXIV_CALL
    now = time.monotonic()
    elapsed = now - _LAST_ARXIV_CALL
    if elapsed < 3.0:
        time.sleep(3.0 - elapsed)
    _LAST_ARXIV_CALL = time.monotonic()


def _redact_exa_key(text: str) -> str:
    key = (os.getenv("EXA_API_KEY") or "").strip()
    if key and key in text:
        text = text.replace(key, "[REDACTED]")
    return text


class RetryableError(Exception):
    """Given. Raise it inside a call to ask with_retry to wait and try again (retry_after in seconds, optional)."""

    def __init__(self, message, retry_after=None):
        super().__init__(message)
        self.retry_after = retry_after


# ---- TODO 1: retry helper ----
def with_retry(fn, *, attempts=5, base=1.0, cap=30.0):
    """Call fn(); when it raises RetryableError, wait and call it again."""
    attempts = max(1, int(attempts))
    cap = max(0.0, float(cap))
    base = max(0.0, float(base))
    for attempt in range(attempts):
        try:
            return fn()
        except Exception as exc:
            retryable = False
            delay = None

            if isinstance(exc, RetryableError):
                retryable = True
                if exc.retry_after is not None:
                    try:
                        delay = float(exc.retry_after)
                    except (ValueError, TypeError):
                        pass
            elif isinstance(exc, httpx.HTTPStatusError):
                if exc.response.status_code in (429, 500, 502, 503, 504):
                    retryable = True
                    ra = exc.response.headers.get("Retry-After")
                    if ra:
                        try:
                            delay = float(ra)
                        except (ValueError, TypeError):
                            pass
            elif isinstance(exc, httpx.TransportError):
                retryable = True

            if not retryable or attempt == attempts - 1:
                raise exc

            if delay is None:
                # Add jitter before applying the cap.  Otherwise a capped
                # backoff could still sleep longer than ``cap``.
                delay = min(cap, base * (2 ** attempt) + random.uniform(0.0, 1.0))
            else:
                delay = min(cap, max(0.0, delay))
            time.sleep(delay)


# ---- TODO 2: arXiv ----
@tool
def arxiv_search(query: str, max_results: int = 10) -> str:
    """Search arXiv papers by keywords, newest first. Returns a JSON list of {id, url, published, title, summary}."""
    try:
        terms = re.findall(r"[\w\-]+", query)
        if not terms:
            return "NO RESULTS"
        search_terms = " AND ".join(f"all:{t}" for t in terms)
        max_res = max(1, min(max_results, 30))

        def _fetch():
            _wait_for_arxiv_politeness()
            params = {
                "search_query": search_terms,
                "sortBy": "submittedDate",
                "sortOrder": "descending",
                "max_results": max_res,
            }
            with httpx.Client(timeout=30.0) as client:
                resp = client.get(ARXIV_URL, params=params)
                if resp.status_code == 429:
                    ra = resp.headers.get("Retry-After")
                    retry_after = float(ra) if ra and ra.isdigit() else 5.0
                    raise RetryableError("arXiv rate limit (429)", retry_after=retry_after)
                resp.raise_for_status()
                return resp.text

        xml_text = with_retry(_fetch, attempts=6, base=2.0, cap=60.0)
        root = ET.fromstring(xml_text)
        ns = {"atom": "http://www.w3.org/2005/Atom"}
        entries = root.findall("atom:entry", ns)
        if not entries:
            return "NO RESULTS"

        records = []
        for entry in entries[:max_res]:
            raw_id = (entry.findtext("atom:id", default="", namespaces=ns)).strip()
            paper_id = raw_id.split("/abs/")[-1] if "/abs/" in raw_id else raw_id
            paper_id = re.sub(r"v\d+$", "", paper_id)
            if not paper_id:
                continue
            url = f"https://arxiv.org/abs/{paper_id}"

            published = (entry.findtext("atom:published", default="", namespaces=ns)).strip()[:10]
            raw_title = entry.findtext("atom:title", default="", namespaces=ns)
            title = " ".join(raw_title.split())

            raw_summary = entry.findtext("atom:summary", default="", namespaces=ns)
            summary = " ".join(raw_summary.split())[:400]

            records.append({
                "id": paper_id,
                "url": url,
                "published": published,
                "title": title,
                "summary": summary,
            })

        if not records:
            return "NO RESULTS"
        return json.dumps(records, ensure_ascii=False)
    except Exception as exc:
        return f"ERROR: {type(exc).__name__}: {exc}"


# ---- TODO 3: Hugging Face ----
@tool
def hf_daily_papers(limit: int = 30, date: str = "", keyword: str = "") -> str:
    """Hugging Face Daily Papers = what is trending in AI research. Returns a JSON list of
    {id, url, published, title, summary, upvotes, github, stars} sorted by upvotes. `date` is YYYY-MM-DD (empty = latest).
    `keyword` filters title/summary; there is no topic search on this endpoint (use hf_search_papers for a topic)."""
    try:
        lim = max(1, min(limit, 100))
        params = {"limit": lim}
        if date and date.strip():
            params["date"] = date.strip()

        def _fetch():
            with httpx.Client(timeout=30.0) as client:
                resp = client.get(HF_DAILY_URL, params=params)
                resp.raise_for_status()
                return resp.json()

        items = with_retry(_fetch, attempts=5, base=1.0, cap=30.0)
        if not items or not isinstance(items, list):
            return "NO RESULTS"

        records = []
        for item in items:
            if not isinstance(item, dict):
                continue
            paper = item.get("paper") if isinstance(item.get("paper"), dict) else item
            paper_id = paper.get("id")
            if not paper_id:
                continue

            title = " ".join(str(paper.get("title") or item.get("title") or "").split())
            summary = " ".join(str(paper.get("summary") or item.get("summary") or "").split())[:400]
            published = str(paper.get("publishedAt") or item.get("publishedAt") or "")[:10]
            upvotes = int(paper.get("upvotes") or item.get("upvotes") or 0)
            github = paper.get("githubRepo") or item.get("githubRepo") or ""
            stars = paper.get("githubStars") or item.get("githubStars") or 0
            url = f"https://huggingface.co/papers/{paper_id}"

            records.append({
                "id": str(paper_id),
                "url": url,
                "published": published,
                "title": title,
                "summary": summary,
                "upvotes": upvotes,
                "github": github,
                "stars": stars,
            })

        if keyword and keyword.strip():
            kw = keyword.strip().lower()
            records = [r for r in records if kw in (r["title"] + " " + r["summary"]).lower()]

        records.sort(key=lambda r: r.get("upvotes", 0), reverse=True)
        records = records[:5]

        if not records:
            return "NO RESULTS"
        return json.dumps(records, ensure_ascii=False)
    except Exception as exc:
        return f"ERROR: {type(exc).__name__}: {exc}"


@tool
def hf_search_papers(query: str, limit: int = 5) -> str:
    """Search Hugging Face papers by topic. Returns a JSON list of
    {id, url, published, title, summary, upvotes, github, stars}."""
    try:
        q = query.strip()
        if not q:
            return "NO RESULTS"
        lim = max(1, min(limit, 50))
        params = {"q": q, "limit": lim}

        def _fetch():
            with httpx.Client(timeout=30.0) as client:
                resp = client.get(HF_SEARCH_URL, params=params)
                resp.raise_for_status()
                return resp.json()

        items = with_retry(_fetch, attempts=5, base=1.0, cap=30.0)
        if not items or not isinstance(items, list):
            return "NO RESULTS"

        records = []
        for item in items:
            if not isinstance(item, dict):
                continue
            paper = item.get("paper") if isinstance(item.get("paper"), dict) else item
            paper_id = paper.get("id")
            if not paper_id:
                continue

            title = " ".join(str(paper.get("title") or item.get("title") or "").split())
            raw_summary = paper.get("ai_summary") or paper.get("summary") or item.get("summary") or ""
            summary = " ".join(str(raw_summary).split())[:400]
            published = str(paper.get("publishedAt") or item.get("publishedAt") or "")[:10]
            upvotes = int(paper.get("upvotes") or item.get("upvotes") or 0)
            github = paper.get("githubRepo") or item.get("githubRepo") or ""
            stars = paper.get("githubStars") or item.get("githubStars") or 0
            url = f"https://huggingface.co/papers/{paper_id}"

            records.append({
                "id": str(paper_id),
                "url": url,
                "published": published,
                "title": title,
                "summary": summary,
                "upvotes": upvotes,
                "github": github,
                "stars": stars,
            })

        records = records[:lim]
        if not records:
            return "NO RESULTS"
        return json.dumps(records, ensure_ascii=False)
    except Exception as exc:
        return f"ERROR: {type(exc).__name__}: {exc}"


# ---- TODO 4: web search / fetch through the Exa MCP endpoint ----
def _call_exa_mcp(tool_name: str, arguments: dict) -> str:
    key = (os.getenv("EXA_API_KEY") or "").strip()
    url = f"{EXA_URL}?exaApiKey={key}" if key else EXA_URL
    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json, text/event-stream",
    }
    payload = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "tools/call",
        "params": {
            "name": tool_name,
            "arguments": arguments,
        },
    }

    def _post():
        with httpx.Client(timeout=60.0) as client:
            resp = client.post(url, headers=headers, json=payload)
            resp.raise_for_status()

            data_obj = None
            for line in resp.text.splitlines():
                line = line.strip()
                if line.startswith("data:"):
                    raw_json = line[5:].strip()
                    try:
                        data_obj = json.loads(raw_json)
                        break
                    except json.JSONDecodeError:
                        pass
            if data_obj is None:
                try:
                    data_obj = resp.json()
                except Exception:
                    raise RuntimeError(f"Unexpected response format from Exa MCP: {resp.text[:200]}")

            if "error" in data_obj:
                err_msg = str(data_obj["error"])
                if "rate limit" in err_msg.lower():
                    raise RetryableError(f"Exa rate limit: {err_msg}", retry_after=20.0)
                raise RuntimeError(f"Exa MCP error: {err_msg}")

            result = data_obj.get("result", {})
            meta = result.get("_meta", {})

            content_items = result.get("content", [])
            text_parts = [c.get("text", "") for c in content_items if isinstance(c, dict) and c.get("type") == "text"]
            combined_text = "\n".join(text_parts)

            if meta.get("rate_limited") or meta.get("rateLimit") or "rate limit" in combined_text.lower():
                raise RetryableError("Exa rate limit encountered in response", retry_after=20.0)

            if result.get("isError"):
                raise RuntimeError(combined_text or "Exa MCP returned an error")

            return combined_text

    return with_retry(_post, attempts=6, base=2.0, cap=60.0)


@tool
def web_search(query: str, objective: str = "", num_results: int = 5) -> str:
    """Search the web (Exa). Describe the ideal page in natural language. Returns clean text of the top results with URLs."""
    try:
        q = query.strip()
        if not q:
            return "NO RESULTS"
        obj = objective.strip() if objective else f"find relevant research papers and surveys on {q}"
        num_res = max(1, min(num_results, 5))
        text = _call_exa_mcp("web_search_exa", {"query": q, "objective": obj, "numResults": num_res})
        if not text or not text.strip():
            return "NO RESULTS"
        return text.strip()[:3000]
    except Exception as exc:
        return _redact_exa_key(f"ERROR: {type(exc).__name__}: {exc}")


@tool
def web_fetch(url: str) -> str:
    """Read the full content of one web page (e.g. an arXiv abstract page) as markdown. Long pages are truncated."""
    try:
        u = url.strip()
        if not u:
            return "NO RESULTS"
        text = _call_exa_mcp("web_fetch_exa", {"urls": [u]})
        if not text or not text.strip():
            return "NO RESULTS"
        return text.strip()[:12000]
    except Exception as exc:
        return _redact_exa_key(f"ERROR: {type(exc).__name__}: {exc}")


# ---- TODO 5: registry (the researcher subagent gets exactly these) ----
SOURCE_TOOLS = [arxiv_search, hf_daily_papers, hf_search_papers, web_search, web_fetch]


if __name__ == "__main__":
    for name, fn, args in [
        ("arxiv_search", arxiv_search, {"query": "world model", "max_results": 3}),
        ("hf_daily_papers", hf_daily_papers, {"limit": 20}),
        ("hf_search_papers", hf_search_papers, {"query": "world model", "limit": 3}),
        ("web_search", web_search, {"query": "survey paper on world models", "num_results": 2}),
        ("web_fetch", web_fetch, {"url": "https://arxiv.org/abs/1803.10122"}),
    ]:
        try:
            print(f"== {name}\n{fn.invoke(args)[:400]}\n")
        except NotImplementedError as exc:
            print(f"== {name}: not implemented yet ({exc})\n")
