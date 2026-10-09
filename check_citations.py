"""check_citations.py - STUDENT IMPLEMENTS `check`.   Runs INSIDE the sandbox (standard library only).

research.py uploads this file to the sandbox and the lead agent runs it with the `execute` tool:
    python3 /tmp/work/research/check_citations.py [report.md] [sources.json]
It must exit 0 and print "OK: ..." when the report is consistent, else print each problem and exit 1.
"""
import json
import sys

REPORT = "/tmp/work/report/report.md"
SOURCES = "/tmp/work/research/sources.json"


import re

_GROUP = re.compile(r"\[(\d+(?:\s*[,–-]\s*\d+)*)\](?!\()")   # [3]  [1, 2]  [1-3]  [2-3]; not [3](link)
_CODE = re.compile(r"(```.*?```|`[^`\n]*`)", re.DOTALL)
_REF_HEADING = re.compile(r"(?m)^##[ \t]+References[ \t]*$")
_REF_LINE = re.compile(r"^\s*\[(\d+)\]\s*(.*)$")


def _group_numbers(group):
    numbers = []
    for part in re.split(r"\s*,\s*", group):
        span = re.fullmatch(r"(\d+)\s*[–-]\s*(\d+)", part)
        if span:
            a, b = int(span.group(1)), int(span.group(2))
            numbers.extend(range(a, b + 1) if 0 <= b - a <= 200 else [a, b])
        elif part.isdigit():
            numbers.append(int(part))
    return numbers


def check(report_text, sources):
    """Return a list of problem strings (empty list = OK)."""
    problems = []

    if not isinstance(sources, list) or len(sources) == 0:
        return ["no sources in sources.json"]

    source_by_n = {}
    seen_urls = set()

    for idx, s in enumerate(sources):
        if not isinstance(s, dict):
            problems.append(f"source item at index {idx} is not an object")
            continue
        n = s.get("n")
        if type(n) is not int:
            problems.append(f"source {s} does not have an integer 'n'")
        elif n in source_by_n:
            problems.append(f"duplicate source number [{n}] in sources.json")
        else:
            source_by_n[n] = s

        url = s.get("url")
        if not isinstance(url, str) or not (url.startswith("http://") or url.startswith("https://")):
            problems.append(f"source [{n}] has missing or invalid URL: {url!r}")
        elif url in seen_urls:
            problems.append(f"duplicate url in sources.json: {url}")
        else:
            seen_urls.add(url)

    matches = list(_REF_HEADING.finditer(report_text))
    if not matches:
        problems.append("missing heading '## References' in report")
        body = report_text
        refs_text = ""
    else:
        body = report_text[:matches[-1].start()]
        refs_text = report_text[matches[-1].end():]

    # Find cited numbers in body only (ignoring code blocks/spans and markdown links)
    segments = _CODE.split(body)
    cited = set()
    for i, segment in enumerate(segments):
        if i % 2:  # odd indices are code blocks or inline code
            continue
        for match in _GROUP.finditer(segment):
            for num in _group_numbers(match.group(1)):
                cited.add(num)

    # Every number in cited must exist in sources.json
    for num in sorted(cited):
        if num not in source_by_n:
            problems.append(f"[{num}] is cited in the text but missing from sources.json")

    # Every source in sources.json must be cited in body
    for num in sorted(source_by_n.keys()):
        if num not in cited:
            problems.append(f"source [{num}] is in sources.json but never cited in report body")

    # Parse lines of References section that start with [n]
    ref_lines = {}
    for line in refs_text.splitlines():
        line_s = line.strip()
        if not line_s:
            continue
        match = _REF_LINE.match(line_s)
        if not match:
            continue
        n = int(match.group(1))
        if n in ref_lines:
            problems.append(f"duplicate reference line for [{n}] in References section")
        else:
            ref_lines[n] = line_s

    # Every source needs exactly one reference line
    for n in sorted(source_by_n.keys()):
        if n not in ref_lines:
            problems.append(f"missing reference line for source [{n}] in References section")

    for n in sorted(ref_lines.keys()):
        if n not in source_by_n:
            problems.append(f"reference [{n}] exists in References section but is not in sources.json")

    # Each reference line holds exactly one URL and matches source's URL
    for n, line_s in sorted(ref_lines.items()):
        if n not in source_by_n:
            continue
        raw_urls = re.findall(r"https?://\S+", line_s)
        clean_urls = [u.rstrip(".,;)>)]\"'") for u in raw_urls]
        if len(clean_urls) == 0:
            problems.append(f"reference line for [{n}] contains no URL")
        elif len(clean_urls) > 1:
            problems.append(f"reference line for [{n}] holds multiple URLs ({len(clean_urls)}), bundled sources not allowed")
        else:
            expected_url = source_by_n[n].get("url")
            if clean_urls[0] != expected_url:
                problems.append(f"reference line for [{n}] URL '{clean_urls[0]}' does not match sources.json URL '{expected_url}'")

    return problems


def main(argv):
    report_path = argv[1] if len(argv) > 1 else REPORT
    sources_path = argv[2] if len(argv) > 2 else SOURCES
    try:
        with open(report_path, encoding="utf-8") as f:
            report = f.read()
        with open(sources_path, encoding="utf-8") as f:
            sources = json.load(f)
    except (OSError, ValueError) as exc:
        print(f"cannot read inputs: {exc}")
        return 1
    problems = check(report, sources)
    if problems:
        print("\n".join(problems))
        return 1
    print(f"OK: {len(sources)} sources, all citations resolve")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
