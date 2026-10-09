"""run_all.py - Automated runner for all 5 preset topics in topics.md."""
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

from research import _validate_sources_for_submission, main as run_research, slugify
from self_check import check_topic, find_meta, load_topics, load_validator

ROOT = Path(__file__).parent
REPORTS = ROOT / "reports"


def strict_check_topic(topic, validator):
    """Run the provided checks plus the submission-only family/URL checks."""
    problems = check_topic(topic, REPORTS, validator)
    if problems:
        return problems
    meta_path, _ = find_meta(topic, REPORTS)
    stem = meta_path.name[: -len(".meta.json")]
    try:
        sources = json.loads((REPORTS / f"{stem}.sources.json").read_text(encoding="utf-8"))
        _validate_sources_for_submission(sources)
    except Exception as exc:  # noqa: BLE001
        return [f"strict source validation: {exc}"]
    return []


def run():
    topics = load_topics()
    validator = load_validator()
    print(f"=== AUTOMATED RUNNER: {len(topics)} TOPICS ===", flush=True)

    for i, topic in enumerate(topics, 1):
        print(f"\n=======================================================", flush=True)
        print(f"[{i}/{len(topics)}] Checking: '{topic}'", flush=True)
        problems = strict_check_topic(topic, validator)
        if not problems:
            print(f"[{i}/{len(topics)}] ALREADY COMPLETED & PASSES CHECKS. Skipping.", flush=True)
            continue

        print(f"[{i}/{len(topics)}] Executing research for: '{topic}'", flush=True)
        retries = 3
        for attempt in range(retries):
            ret = run_research(topic)
            if ret == 0:
                problems = strict_check_topic(topic, validator)
                if not problems:
                    print(f"[{i}/{len(topics)}] SUCCESS! Topic passed all checks.", flush=True)
                    break
                else:
                    print(f"[{i}/{len(topics)}] Topic finished with problems: {problems}. Retrying...", flush=True)
            else:
                print(f"[{i}/{len(topics)}] Topic exited with code {ret}. Retrying attempt {attempt+1}/{retries}...", flush=True)
            time.sleep(10)

        # Politeness cooling break between topics to let rate limit window recover
        print(f"[{i}/{len(topics)}] Cooling down for 20s before next topic...", flush=True)
        time.sleep(20)

    print("\n=======================================================", flush=True)
    print("=== RUNNING FINAL SELF_CHECK ===", flush=True)
    subprocess.run([sys.executable, str(ROOT / "self_check.py")])


if __name__ == "__main__":
    run()

