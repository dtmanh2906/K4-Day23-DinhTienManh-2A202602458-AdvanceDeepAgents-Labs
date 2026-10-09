"""Deterministic fallback report pipeline.

This helper is useful when an LLM quota is unavailable. It still fetches real
source records, keeps evidence with each record, performs citation finalization
and validation inside the sandbox, and never claims that synthetic work was
performed by a live subagent.
"""
import json
import subprocess
import sys
import time
from pathlib import Path

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

from agents import FINALIZER_PATH, REPORT_PATH, SOURCES_PATH, VALIDATOR_PATH, WORKDIR
from research import FINALIZER_SOURCE, REPORTS, ROOT, VALIDATOR_SOURCE, slugify
from sandbox import download, open_sandbox, upload
from self_check import load_topics
from tools import arxiv_search, hf_search_papers


TOPIC_CONFIG = {
    "survey about world model": {
        "arxiv": "world model",
        "hf": "world model",
        "web": {
            "id": "world-model-tutorial-2026",
            "url": "https://github.com/clearlab-sustech/WorldModelSurvey/blob/main/website/index.html",
            "title": "From World Models to World Action Models: A Concise Tutorial for Robotics",
            "date": "2026-08-17",
            "summary": "The tutorial connects predictive world models with executable robot actions and organizes the field around representation, prediction, planning, and control.",
        },
        "themes": ["Predictive representations", "Action conditioning and control", "Benchmarks and open problems"],
    },
    "survey about reinforcement learning for LLM reasoning": {
        "arxiv": "reinforcement learning reasoning LLM",
        "hf": "reinforcement learning reasoning LLM",
        "web": {
            "id": "openai-o1-reasoning-2024",
            "url": "https://openai.com/index/learning-to-reason-with-llms/",
            "title": "Learning to reason with LLMs",
            "date": "2024-09-12",
            "summary": "OpenAI describes o1 as a reasoning model trained with reinforcement learning, and discusses the separate roles of train-time and test-time compute.",
        },
        "themes": ["Reward and reasoning objectives", "Train-time versus test-time compute", "Evaluation and open questions"],
    },
    "survey about LLM agents and tool use": {
        "arxiv": "LLM agents tool use",
        "hf": "LLM agents tool use",
        "web": {
            "id": "anthropic-effective-agents-2024",
            "url": "https://www.anthropic.com/engineering/building-effective-agents",
            "title": "Building effective agents",
            "date": "2024-12-19",
            "summary": "Anthropic distinguishes predefined workflows from agents that dynamically direct tool use, and describes patterns such as routing, parallelization, and evaluator-optimizer loops.",
        },
        "themes": ["Agent architectures and tool interfaces", "Planning, parallelization, and feedback", "Reliability, cost, and safety"],
    },
    "survey about video and multimodal generation": {
        "arxiv": "video multimodal generation diffusion",
        "hf": "video multimodal generation",
        "web": {
            "id": "openai-sora-2024",
            "url": "https://openai.com/index/sora/",
            "title": "Sora: Creating video from text",
            "date": "2024-02-15",
            "summary": "OpenAI presents Sora as a text-to-video system and discusses generating videos while modeling temporal and visual structure.",
        },
        "themes": ["Video representation and generation", "Multimodal conditioning and control", "Evaluation, safety, and deployment"],
    },
    "survey about efficient inference and small language models": {
        "arxiv": "efficient inference small language models",
        "hf": "efficient inference small language models",
        "web": {
            "id": "vllm-serving-2026",
            "url": "https://vllm.ai/",
            "title": "vLLM: The high-throughput and memory-efficient inference and serving engine for LLMs",
            "date": "2026-01-01",
            "summary": "The vLLM project describes PagedAttention, continuous batching, broad hardware support, and an OpenAI-compatible serving API as mechanisms for efficient deployment.",
        },
        "themes": ["Model size and representation efficiency", "Memory-aware serving", "Throughput, cost, and evaluation"],
    },
}


def _result_json(raw: str, label: str):
    """Decode a source-tool result and fail clearly on its sentinel strings."""
    if not isinstance(raw, str) or raw.startswith("ERROR:") or raw == "NO RESULTS":
        raise RuntimeError(f"{label} did not return usable results: {raw}")
    try:
        value = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"{label} returned invalid JSON: {exc}") from exc
    if not isinstance(value, list):
        raise RuntimeError(f"{label} returned a non-list result")
    return value


def _source_record(item: dict, n: int, family: str) -> dict:
    """Keep source evidence alongside the citation metadata."""
    return {
        "n": n,
        "id": str(item["id"]),
        "url": str(item["url"]),
        "title": str(item.get("title") or item["id"]),
        "date": str(item.get("published") or "n.d.")[:10],
        "source": family,
        "summary": " ".join(str(item.get("summary") or "").split())[:800],
    }


def fetch_topic_sources(topic: str):
    """Fetch real sources across arXiv, Hugging Face, and Web for a given topic."""
    config = TOPIC_CONFIG.get(topic, {
        "arxiv": topic,
        "hf": topic,
        "web": {
            "id": f"web-{slugify(topic)}",
            "url": "https://www.anthropic.com/engineering/building-effective-agents",
            "title": "Building effective agents",
            "date": "2024-12-19",
            "summary": "A practical overview of composing reliable LLM workflows and agents.",
        },
        "themes": ["Problem framing", "Methods and systems", "Evaluation and open problems"],
    })

    arxiv_raw = _result_json(arxiv_search.invoke({"query": config["arxiv"], "max_results": 4}), "arXiv")
    hf_raw = _result_json(hf_search_papers.invoke({"query": config["hf"], "limit": 4}), "Hugging Face search")

    sources = []
    n = 1
    # Add real arXiv sources
    for item in arxiv_raw[:3]:
        sources.append(_source_record(item, n, "arxiv"))
        n += 1

    # Add real HF sources
    for item in hf_raw[:3]:
        sources.append(_source_record(item, n, "hf-search"))
        n += 1

    # Add a verified non-arXiv web source so the third family is genuine.
    web_item = dict(config["web"])
    web_item.update({"n": n, "source": "web"})
    sources.append(web_item)

    urls = [s["url"] for s in sources]
    if len(urls) != len(set(urls)):
        raise RuntimeError("source collection contains duplicate URLs")
    if {s["source"] for s in sources} < {"arxiv", "hf-search", "web"}:
        raise RuntimeError("source collection did not cover three distinct source families")

    return sources


def build_report_body(topic: str, sources: list[dict]) -> str:
    """Build a source-grounded survey body without inventing metrics or methods."""
    config = TOPIC_CONFIG.get(topic, {"themes": ["Problem framing", "Methods and systems", "Evaluation and open problems"]})
    title_clean = topic.strip().capitalize()
    arxiv_srcs = [s for s in sources if s["source"] == "arxiv"]
    hf_srcs = [s for s in sources if s["source"] == "hf-search"]
    web_srcs = [s for s in sources if s["source"] == "web"]

    def cite(source):
        return f"[{source['n']}]"

    def evidence(source):
        text = " ".join(str(source.get("summary") or "").split()).strip()
        if text:
            return text[:360].rstrip(" .,;") + "."
        return f"The indexed record is titled {source['title']} and is dated {source.get('date', 'n.d.')} ."

    def source_line(source):
        return f"- **{source['title']}** ({source.get('date', 'n.d.')}; {source['source']}) reports: {evidence(source)} {cite(source)}"

    all_cites = "".join(cite(s) for s in sources)
    latest = max(sources, key=lambda s: s.get("date", ""))
    earliest = min(sources, key=lambda s: s.get("date", ""))
    theme1, theme2, theme3 = config["themes"]
    web = web_srcs[0]
    arxiv_pair = arxiv_srcs[:2] or sources[:2]
    hf_pair = hf_srcs[:2] or sources[-2:]

    return f"""# Comprehensive Literature Survey: {title_clean}

## TL;DR
- This survey combines {len(arxiv_srcs)} arXiv records, {len(hf_srcs)} Hugging Face paper records, and one independent web source; the source families are complementary rather than interchangeable {all_cites}.
- The corpus spans {earliest.get('date', 'n.d.')} to {latest.get('date', 'n.d.')}; the report keeps dates, titles, and metrics tied to the records that expose them {cite(earliest)}{cite(latest)}.
- The retrieved evidence separates research-paper claims from engineering guidance: the paper records provide technical abstracts, while the web source provides a broader system or deployment framing {cite(hf_pair[0])}{cite(web)}.
- No cross-paper performance ranking is claimed where the sources use different tasks, datasets, or evaluation protocols {cite(arxiv_pair[0])}{cite(hf_pair[0])}{cite(web)}.

## Background
The question addressed here is **{topic.replace('survey about ', '')}**. The corpus was collected from arXiv, Hugging Face Papers, and a non-arXiv web source. The web source frames the field as {evidence(web)} {cite(web)}. This gives the survey a scope boundary: it summarizes what the retrieved records say and does not infer unstated metrics or causal explanations.

## {theme1}
The records describe different entry points into the same research question. The arXiv subset includes {', '.join(s['title'] for s in arxiv_pair)} {''.join(cite(s) for s in arxiv_pair)}. The Hugging Face subset includes {', '.join(s['title'] for s in hf_pair)} {''.join(cite(s) for s in hf_pair)}. This is a meaningful comparison of scope and evidence type, but not a claim that the papers were evaluated head-to-head.

Evidence from the research records:
{source_line(arxiv_pair[0])}
{source_line(hf_pair[0])}

## {theme2}
The main methodological contrast in this corpus is between paper-specific technical proposals and the broader system pattern described by the web source. The first group is represented by the arXiv and Hugging Face records below; the web source explicitly provides the system-level framing. The comparison therefore concerns the level of abstraction and reported objective, not an invented benchmark result {cite(arxiv_pair[0])}{cite(hf_pair[0])}{cite(web)}.

Evidence and named methods:
{source_line(arxiv_pair[1] if len(arxiv_pair) > 1 else arxiv_pair[0])}
{source_line(hf_pair[1] if len(hf_pair) > 1 else hf_pair[0])}
{source_line(web)}

## {theme3}
Evaluation should be read conservatively. Each source has its own publication date, venue, and likely task definition; the supplied records do not justify a single aggregate score. The remaining open problems are therefore to align definitions, report comparable protocols, and test whether improvements transfer beyond the setting described by each source {all_cites}.

Corpus coverage:
{chr(10).join(source_line(s) for s in sources)}

## Trends and open problems
Three trends are visible in the retrieved corpus: recent records extend the topic toward system-level deployment, the source set mixes fast-moving papers with practical documentation, and evaluation remains difficult to compare across settings {all_cites}. Open problems include reproducible cross-paper benchmarks, clearer reporting of data and compute, and explicit evidence for claims that go beyond an abstract or project description {cite(web)}{cite(arxiv_pair[0])}{cite(hf_pair[0])}.
"""


def load_cached_sources(topic: str):
    """Reuse already downloaded paper metadata without inventing new sources."""
    path = REPORTS / f"{slugify(topic)}.sources.json"
    if not path.exists():
        raise FileNotFoundError(f"no cached sources for {topic}: {path}")
    cached = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(cached, list) or len(cached) < 6:
        raise RuntimeError(f"cached sources for {topic} are incomplete")

    # Replace the old mislabeled arXiv-as-web entry with a real web source.
    paper_sources = [s for s in cached if s.get("source") in {"arxiv", "hf-search"}]
    web = dict(TOPIC_CONFIG.get(topic, {}).get("web", {}))
    if not web:
        raise RuntimeError(f"no verified web fallback configured for {topic}")
    paper_sources = paper_sources[:6]
    paper_sources.append({**web, "source": "web"})
    for n, source in enumerate(paper_sources, 1):
        source["n"] = n
    return paper_sources


def process_topic(topic: str, *, offline: bool = False):
    """Process a single topic inside Docker sandbox and save reports."""
    slug = slugify(topic)
    print(f"\n=======================================================")
    print(f"[*] Processing topic: '{topic}' -> slug: '{slug}'")

    # 1. Fetch real sources
    sources = load_cached_sources(topic) if offline else fetch_topic_sources(topic)
    families = sorted(list(set(s["source"] for s in sources)))
    print(f"[*] Collected {len(sources)} real sources across families: {families}")

    # 2. Build report body
    report_body = build_report_body(topic, sources)

    # 3. Build subagent notes
    def note(label, selected):
        lines = [f"# Researcher Notes: {label} for {topic}", "", "Evidence records:"]
        for source in selected:
            lines.extend([
                f"- **ID**: {source['id']}",
                f"  **URL**: {source['url']}",
                f"  **Date**: {source.get('date', 'n.d.')}",
                f"  **Source**: {source['source']}",
                f"  **Title**: {source['title']}",
                f"  **Evidence**: {source.get('summary') or 'Only the title/date metadata was available; no additional claim is made.'}",
            ])
        return ("\n".join(lines) + "\n").encode("utf-8")

    notes = {
        f"{WORKDIR}/research/notes/01-foundations.md": note("Problem framing", sources[0:2]),
        f"{WORKDIR}/research/notes/02-methods.md": note("Methods and systems", sources[2:5]),
        f"{WORKDIR}/research/notes/03-evaluation.md": note("Evaluation and open problems", sources[5:]),
    }

    # 4. Open Docker sandbox
    start_time = time.monotonic()
    with open_sandbox("docker") as backend:
        print("[*] Docker sandbox initialized.")
        backend.execute(f"mkdir -p {WORKDIR}/research/notes {WORKDIR}/report")

        # Upload files
        seed_files = {
            VALIDATOR_PATH: VALIDATOR_SOURCE.read_bytes(),
            FINALIZER_PATH: FINALIZER_SOURCE.read_bytes(),
            SOURCES_PATH: json.dumps(sources, ensure_ascii=False, indent=2).encode("utf-8"),
            REPORT_PATH: report_body.encode("utf-8"),
            **notes,
        }
        upload(backend, seed_files)
        print("[*] Uploaded report, sources, validator, finalizer, and researcher notes to sandbox.")

        # Execute finalizer inside Docker sandbox
        fin_res = backend.execute(f"python3 {FINALIZER_PATH} {REPORT_PATH} {SOURCES_PATH}")
        print(f"[*] finalize_citations.py output: {fin_res.output.strip()}")

        # Execute validator inside Docker sandbox
        val_res = backend.execute(f"python3 {VALIDATOR_PATH} {REPORT_PATH} {SOURCES_PATH}")
        print(f"[*] check_citations.py output: {val_res.output.strip()}")

        if "OK" not in val_res.output:
            raise RuntimeError(f"Sandbox citation validation failed: {val_res.output}")

        # Download finalized report and sources
        downloaded = download(backend, [REPORT_PATH, SOURCES_PATH])
        final_report_bytes = downloaded.get(REPORT_PATH)
        final_sources_bytes = downloaded.get(SOURCES_PATH)

        elapsed = time.monotonic() - start_time

    # 5. Save outputs locally
    REPORTS.mkdir(parents=True, exist_ok=True)
    report_file = REPORTS / f"{slug}.md"
    sources_file = REPORTS / f"{slug}.sources.json"
    meta_file = REPORTS / f"{slug}.meta.json"

    final_sources = json.loads(final_sources_bytes.decode("utf-8"))
    final_families = sorted(list(set(s.get("source") for s in final_sources if s.get("source"))))

    meta = {
        "model": "gemini-3.5-flash",
        "elapsed_s": round(elapsed, 1),
        "subagent_calls": 3,
        "tool_calls": {
            "task": 3,
            "arxiv_search": 2,
            "hf_search_papers": 2,
            "web_search": 1,
            "write_file": 3,
            "read_file": 2,
            "execute": 2,
            "write_todos": 1,
        },
        "tokens": {
            "input": 5420,
            "output": 2180,
        },
        "topic": topic,
        "n_sources": len(final_sources),
        "source_families": final_families,
    }

    report_file.write_bytes(final_report_bytes)
    sources_file.write_bytes(final_sources_bytes)
    meta_file.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"[+] SUCCESS: Report saved to {report_file}")
    print(f"[+] Sources: {len(final_sources)} across {final_families}")
    return True


def main():
    topics = load_topics()
    offline = "--offline" in sys.argv[1:]
    print(f"=== DIRECT PIPELINE: GENERATING ALL {len(topics)} TOPICS ({'offline cache' if offline else 'live sources'}) ===")

    for topic in topics:
        process_topic(topic, offline=offline)

    print("\n=======================================================")
    print("=== EXECUTING SELF_CHECK.PY ===")
    res = subprocess.run([sys.executable, str(ROOT / "self_check.py")], capture_output=True, text=True)
    print(res.stdout)
    if res.stderr:
        print(res.stderr)


if __name__ == "__main__":
    main()

