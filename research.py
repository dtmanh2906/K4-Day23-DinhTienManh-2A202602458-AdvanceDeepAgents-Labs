"""research.py - STUDENT IMPLEMENTS.  The main script.   Guide: GUIDE.md, part 3.

Usage:  python research.py "survey about world model"
Result: reports/<slug>.md   reports/<slug>.sources.json   reports/<slug>.meta.json
"""


import json
import os
import re
import sys
import time
from collections import Counter
from pathlib import Path
from urllib.parse import urlparse

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

from agents import FINALIZER_PATH, REPORT_PATH, SOURCES_PATH, VALIDATOR_PATH, WORKDIR, build_lead_agent
from model import make_model
from sandbox import download, open_sandbox, upload

ROOT = Path(__file__).parent
REPORTS = ROOT / "reports"
VALIDATOR_SOURCE = ROOT / "check_citations.py"
FINALIZER_SOURCE = ROOT / "finalize_citations.py"   # provided: uploaded next to your validator


def slugify(topic):
    """Turn a topic into a safe file name: lower case, runs of non-word characters become one "-", max 60 chars,
    never empty (fall back to "topic"). The topic is user input: "../../x" must not escape reports/."""
    if not topic or not isinstance(topic, str):
        return "topic"
    s = topic.strip().lower()
    s = re.sub(r"[^\w]+", "-", s).strip("-")
    if not s:
        return "topic"
    return s[:60].rstrip("-") or "topic"


def build_prompt(topic):
    """The user message sent to the lead agent."""
    return (
        f"Conduct a comprehensive, empirical scientific literature survey on the topic: '{topic.strip()}'.\n\n"
        "STRICT WORKFLOW TO FOLLOW:\n"
        "1. Plan with `write_todos` and deconstruct the topic into at least 3 independent sub-questions.\n"
        "2. Delegate each sub-question to `researcher` subagents via `task` in parallel (at least 3 calls). "
        "Include target notes path (/tmp/work/research/notes/<NN>-<slug>.md), note format, and require at least 2 source families per subagent.\n"
        "3. Review notes and merge them into /tmp/work/research/sources.json. Ensure at least 3 source families (arxiv, hf-daily, hf-search, web) are covered.\n"
        "4. Write the survey report body into /tmp/work/report/report.md synthesizing across papers with inline citations [n]. "
        "DO NOT write the `## References` section yourself.\n"
        "5. Run `python3 /tmp/work/research/finalize_citations.py` using `execute` to generate `## References` and clean sources.\n"
        "6. Run `python3 /tmp/work/research/check_citations.py` using `execute` and resolve any issues until it prints OK.\n"
        "7. Spot-check 2-3 claims using the `citation-checker` subagent.\n"
    )


def summarize(messages, elapsed, model_name):
    """Return {"model", "elapsed_s", "subagent_calls", "tool_calls": {name: count}, "tokens": {"input", "output"}}."""
    tool_counter = Counter()
    subagent_calls = 0
    input_tokens = 0
    output_tokens = 0

    for msg in messages:
        tool_calls = []
        usage = None
        if isinstance(msg, dict):
            tool_calls = msg.get("tool_calls") or []
            usage = msg.get("usage_metadata") or msg.get("response_metadata", {}).get("token_usage")
        else:
            tool_calls = getattr(msg, "tool_calls", None) or []
            usage = getattr(msg, "usage_metadata", None) or getattr(msg, "response_metadata", {}).get("token_usage", None)

        for tc in tool_calls:
            name = tc.get("name") if isinstance(tc, dict) else getattr(tc, "name", str(tc))
            if name:
                tool_counter[name] += 1
                if name == "task":
                    subagent_calls += 1

        if usage and isinstance(usage, dict):
            input_tokens += int(usage.get("input_tokens") or usage.get("prompt_tokens") or 0)
            output_tokens += int(usage.get("output_tokens") or usage.get("completion_tokens") or 0)

    return {
        "model": model_name,
        "elapsed_s": round(float(elapsed), 1),
        "subagent_calls": subagent_calls,
        "tool_calls": dict(tool_counter),
        "tokens": {
            "input": input_tokens,
            "output": output_tokens,
        },
    }


def save_outputs(backend, topic, messages, elapsed, model_name, reports_dir=REPORTS):
    """Download the report from the sandbox and write the three files into reports_dir. Return the report path."""
    files = download(backend, [REPORT_PATH, SOURCES_PATH])
    report_bytes = files.get(REPORT_PATH)
    sources_bytes = files.get(SOURCES_PATH)

    if report_bytes is None or len(report_bytes.strip()) == 0:
        raise RuntimeError(f"Report file {REPORT_PATH} is missing or empty in sandbox")
    if sources_bytes is None or len(sources_bytes.strip()) == 0:
        raise RuntimeError(f"Sources file {SOURCES_PATH} is missing or empty in sandbox")

    try:
        sources_data = json.loads(sources_bytes.decode("utf-8"))
        if not isinstance(sources_data, list):
            raise ValueError("sources.json must be a JSON list")
    except Exception as exc:
        raise RuntimeError(f"Invalid sources.json content: {exc}")

    _validate_sources_for_submission(sources_data)
    source_families = sorted({s.get("source") for s in sources_data if isinstance(s, dict) and s.get("source")})
    meta = summarize(messages, elapsed, model_name)
    if meta["subagent_calls"] < 3:
        raise RuntimeError(f"lead delegated only {meta['subagent_calls']} subagent tasks; need at least 3")
    meta["topic"] = topic
    meta["n_sources"] = len(sources_data)
    meta["source_families"] = source_families

    reports_dir = Path(reports_dir)
    reports_dir.mkdir(parents=True, exist_ok=True)
    slug = slugify(topic)

    report_file = reports_dir / f"{slug}.md"
    sources_file = reports_dir / f"{slug}.sources.json"
    meta_file = reports_dir / f"{slug}.meta.json"

    sources_file.write_text(json.dumps(sources_data, ensure_ascii=False, indent=2), encoding="utf-8")
    meta_file.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    report_file.write_text(report_bytes.decode("utf-8"), encoding="utf-8")

    return report_file


def _validate_sources_for_submission(sources_data):
    """Reject misleading metadata before anything is written to reports/."""
    allowed = {"arxiv", "hf-daily", "hf-search", "web"}
    urls = set()
    families = set()
    for source in sources_data:
        if not isinstance(source, dict):
            raise RuntimeError("sources.json contains a non-object source")
        family = source.get("source")
        url = source.get("url")
        if family not in allowed:
            raise RuntimeError(f"invalid source family: {family!r}")
        if not isinstance(url, str) or url in urls:
            raise RuntimeError(f"missing or duplicate source URL: {url!r}")
        urls.add(url)
        families.add(family)
        if family == "arxiv" and not url.startswith("https://arxiv.org/abs/"):
            raise RuntimeError(f"arxiv source has non-arXiv URL: {url}")
        if family.startswith("hf-") and not url.startswith("https://huggingface.co/papers/"):
            raise RuntimeError(f"Hugging Face source has non-HF URL: {url}")
        if family == "web" and (
            url.startswith("https://arxiv.org/abs/")
            or url.startswith("https://huggingface.co/papers/")
        ):
            raise RuntimeError(f"web source is mislabeled as a paper-family URL: {url}")
        if urlparse(url).scheme not in {"http", "https"}:
            raise RuntimeError(f"source URL is not HTTP(S): {url}")
    if len(families) < 3:
        raise RuntimeError(f"only {len(families)} source families; need at least 3")


def main(topic):
    """Return the process exit code (0 ok, 1 failed run, 2 no topic)."""
    t = (topic or "").strip()
    if not t:
        print("Usage: python research.py '<topic>'", file=sys.stderr)
        return 2

    model = make_model()
    model_name = os.getenv("LAB_MODEL", "model")
    start = time.monotonic()

    with open_sandbox() as backend:
        backend.execute(f"mkdir -p {WORKDIR}/research/notes {WORKDIR}/report")
        upload(backend, {
            VALIDATOR_PATH: VALIDATOR_SOURCE.read_bytes(),
            FINALIZER_PATH: FINALIZER_SOURCE.read_bytes(),
        })
        agent = build_lead_agent(backend, model)
        try:
            print(f"[START] Beginning deep research for topic: '{t}'", flush=True)
            messages = []
            for chunk in agent.stream(
                {"messages": [{"role": "user", "content": build_prompt(t)}]},
                config={"recursion_limit": 1000},
                stream_mode="values",
            ):
                cur_msgs = chunk.get("messages", [])
                if len(cur_msgs) > len(messages):
                    for new_msg in cur_msgs[len(messages):]:
                        tool_calls = getattr(new_msg, "tool_calls", None) or []
                        if tool_calls:
                            for tc in tool_calls:
                                name = tc.get("name") if isinstance(tc, dict) else getattr(tc, "name", str(tc))
                                args_val = tc.get("args") if isinstance(tc, dict) else getattr(tc, "args", "")
                                print(f"[LEAD TOOL CALL] {name}: {str(args_val)[:140]}", flush=True)
                        elif getattr(new_msg, "type", "") == "tool":
                            tname = getattr(new_msg, "name", "tool")
                            tcontent = str(getattr(new_msg, "content", ""))
                            print(f"[TOOL RESULT {tname}] {tcontent[:120]}...", flush=True)
                        elif getattr(new_msg, "type", "") == "ai" and getattr(new_msg, "content", ""):
                            print(f"[LEAD] {str(new_msg.content)[:180]}...", flush=True)
                    messages = cur_msgs

            elapsed = time.monotonic() - start
            ls_check = backend.execute("find /tmp/work -type f")
            print(f"[SANDBOX FILES]\n{ls_check.output}", flush=True)
            out_path = save_outputs(backend, t, messages, elapsed, model_name)
            print(f"SUCCESS: Report saved to {out_path}", flush=True)
            return 0
        except Exception as exc:
            print(f"FAILED: {exc}", file=sys.stderr, flush=True)
            return 1


if __name__ == "__main__":
    sys.exit(main(" ".join(sys.argv[1:])))
