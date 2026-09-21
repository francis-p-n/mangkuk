#!/usr/bin/env python3
"""Check the project against the claims it makes.

    python eval/rubric.py              # one pass
    python eval/rubric.py --loop       # re-run until every criterion passes
    python eval/rubric.py --only 1 2   # just those criteria

The claims table in docs/validation.md is the rubric. The numbers it
states are the acceptance thresholds, so this reads them from there rather
than repeating them here: edit a claim and this starts checking the new
value. A rubric kept in two places drifts, and the copy that drifts is
always the one nobody runs.

Exit status is 0 only when every selected criterion passes.
"""
from __future__ import annotations

import argparse
import re
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CLAIMS = ROOT / "docs" / "validation.md"
PY = sys.executable
TIMEOUT = 600          # a hung eval must not hang the loop


class RubricError(RuntimeError):
    """The claims table does not state the number this criterion needs."""


# ---------------------------------------------------------------- reading it

def readme_text() -> dict[str, str]:
    """The claims table in docs/validation.md, as {claim: value}.

    A table rather than prose. The first version regexed sentences out of the
    README, so rewrapping a paragraph could stop a criterion being found - a
    silent pass, which is the worst way for a check to fail. It also meant the
    rubric died when the README became a submission front page; the evidence
    moved to docs/validation.md and this followed it.
    """
    try:
        raw = CLAIMS.read_text(encoding="utf-8")
    except OSError as exc:
        raise RubricError(f"cannot read {CLAIMS.name}: {exc}") from exc

    rows: dict[str, str] = {}
    for line in raw.splitlines():
        m = re.match(r"\|\s*([A-Za-z][A-Za-z \-]+?)\s*\|\s*([\d/,]+)\s*\|$",
                     line.strip())
        if m:
            rows[m.group(1).strip().lower()] = m.group(2).strip()
    if not rows:
        raise RubricError(
            f"{CLAIMS.name} has no claims table - there is nothing to check "
            f"the project against"
        )
    return rows


def claim(key: str, rows: dict[str, str], what: str) -> tuple[int, ...]:
    """Pull the number(s) a claim commits to, or say which claim is gone."""
    if key not in rows:
        raise RubricError(
            f"the claims table no longer states {what} (row {key!r}), so this "
            f"criterion cannot be checked"
        )
    return tuple(int(part.replace(",", "")) for part in rows[key].split("/"))


# ---------------------------------------------------------------- running it

@dataclass
class Outcome:
    ok: bool
    detail: str
    error: str = ""


@dataclass
class Criterion:
    num: int
    name: str
    quote: str                       # what the claims table states
    run: object                      # () -> Outcome
    last: Outcome | None = field(default=None, repr=False)


def shell(*args: str, timeout: int = TIMEOUT) -> tuple[int, str]:
    """Run a project command, capturing everything, never blocking forever."""
    try:
        p = subprocess.run(
            [PY, *args], cwd=ROOT, timeout=timeout,
            capture_output=True, text=True, encoding="utf-8", errors="replace",
        )
    except subprocess.TimeoutExpired:
        return 124, f"TIMEOUT after {timeout}s"
    except OSError as exc:
        return 127, f"could not start: {exc}"
    return p.returncode, (p.stdout or "") + (p.stderr or "")


def number(out: str, pattern: str) -> int | None:
    m = re.search(pattern, out, re.I | re.M)
    return int(m.group(1).replace(",", "")) if m else None


def broken(code: int, out: str) -> Outcome | None:
    """Tell "the project could not run" apart from "the project ran badly".

    Both fail the criterion, but only one of them is a clue about the code
    under test - the other is a clue about the machine, and reporting it as
    "no result line" sends someone hunting in the wrong file.
    """
    if code == 124:
        return Outcome(False, "TIMED OUT - no result", out.strip()[:200])
    if code == 127:
        return Outcome(False, "COULD NOT START", out.strip()[:200])
    return None


# ---------------------------------------------------------------- criteria

def build(text: dict[str, str]) -> list[Criterion]:
    crits: list[Criterion] = []

    # 1 - test suite
    (want_tests,) = claim("tests passing", text, "a test count")

    def c1() -> Outcome:
        code, out = shell("-m", "pytest", "tests", "-q")
        stop = broken(code, out)
        if stop:
            return stop
        got = number(out, r"(\d+)\s+passed")
        failed = number(out, r"(\d+)\s+failed") or 0
        if got is None:
            return Outcome(False, "no result line", out.strip()[-400:])
        if failed:
            return Outcome(False, f"{got} passed, {failed} FAILED", out.strip()[-600:])
        if got < want_tests:
            return Outcome(False, f"{got} passed, the claims table states {want_tests}")
        drift = f"  (the claims table states {want_tests})" if got != want_tests else ""
        return Outcome(code == 0, f"{got} passed{drift}")

    crits.append(Criterion(1, "Test suite", f"{want_tests} passing", c1))

    # 2 - defect injection
    (want_inj,) = claim("defects injected", text, "an injected count")
    (want_caught,) = claim("defects caught", text, "a caught count")

    def c2() -> Outcome:
        code, out = shell("eval/mutation.py")
        stop = broken(code, out)
        if stop:
            return stop
        inj = number(out, r"injected defects\s*:\s*([\d,]+)")
        caught = number(out, r"^caught\s+:\s*([\d,]+)")
        clean = number(out, r"caught cleanly\s*:\s*([\d,]+)")
        ctrl = number(out, r"control failures\s*:\s*([\d,]+)")
        if inj is None or caught is None:
            return Outcome(False, "could not read totals", out.strip()[-400:])
        bad = []
        if caught < want_caught:
            bad.append(f"caught {caught}/{inj}, the claims table states {want_caught}")
        if ctrl:
            bad.append(f"{ctrl} control failure(s)")
        if clean is not None and clean < caught:
            bad.append(f"only {clean} caught cleanly")
        detail = f"{caught}/{inj} caught, {clean} cleanly, {ctrl} control failures"
        return Outcome(not bad and code == 0, detail, "; ".join(bad))

    crits.append(Criterion(2, "Defect injection",
                           f"{want_inj} injected, {want_caught} caught", c2))

    # 3 - clerk's-eye cases
    (want_cases,) = claim("desk cases", text, "a desk-case count")
    (want_missed,) = claim("desk cases missed", text, "a missed count")
    (want_alarms,) = claim("desk cases false alarms", text,
                           "a false-alarm count")

    def c3() -> Outcome:
        code, out = shell("eval/desk_cases.py")
        stop = broken(code, out)
        if stop:
            return stop
        cases = number(out, r"^cases\s*:\s*(\d+)")
        missed = number(out, r"MISSED\s*:\s*(\d+)")
        alarms = number(out, r"FALSE ALARMS\s*:\s*(\d+)")
        if None in (cases, missed, alarms):
            return Outcome(False, "could not read summary", out.strip()[-400:])
        bad = []
        if missed > want_missed:
            bad.append(f"{missed} missed (claimed: {want_missed})")
        if alarms > want_alarms:
            bad.append(f"{alarms} false alarms (claimed: {want_alarms})")
        if cases < want_cases:
            bad.append(f"only {cases} cases (claimed: {want_cases})")
        return Outcome(not bad and code == 0,
                       f"{cases} cases, {missed} missed, {alarms} false alarms",
                       "; ".join(bad))

    crits.append(Criterion(3, "Clerk's-eye cases",
                           f"{want_cases} variations, {want_missed} missed, "
                           f"{want_alarms} false alarms", c3))

    # 4 - the constructed edge-case block
    split = claim("edge block split", text, "the edge-block split")

    def c4() -> Outcome:
        code, out = shell("-m", "pytest", "tests/test_pipeline.py", "-q",
                          "-k", "constructed or edge or block or escalation")
        stop = broken(code, out)
        if stop:
            return stop
        got = number(out, r"(\d+)\s+passed")
        if number(out, r"(\d+)\s+failed"):
            return Outcome(False, "edge-block test FAILED", out.strip()[-600:])
        if not got:
            return Outcome(False, "no edge-block test ran - the pin is gone",
                           out.strip()[-400:])
        return Outcome(code == 0,
                       f"{got} test(s) pin the {'/'.join(map(str, split))} split")

    crits.append(Criterion(4, "Edge-case block",
                           f"resolves {'/'.join(map(str, split))}", c4))

    # 5 - no-ground-truth audit
    (want_res,) = claim("classifier residue", text, "the residue count")
    (want_total,) = claim("corpus emails", text, "the corpus size")

    def c5() -> Outcome:
        code, out = shell("eval/audit.py")
        stop = broken(code, out)
        if stop:
            return stop
        m = re.search(r"low-confidence residue:\s*(\d+)\s*/\s*(\d+)", out, re.I)
        if not m:
            return Outcome(False, "audit produced no residue line",
                           out.strip()[-400:])
        res, total = int(m.group(1)), int(m.group(2))
        if total != want_total:
            return Outcome(False,
                           f"corpus is {total} emails, the claims table says {want_total}")
        if res > want_res:
            return Outcome(False, f"residue grew to {res} (claimed: {want_res}) - "
                                  f"rules now decide less than claimed")
        return Outcome(code == 0, f"{res}/{total} residue "
                                  f"({100 * (total - res) / total:.1f}% by rules)")

    crits.append(Criterion(5, "No-ground-truth audit",
                           f"{want_res} of {want_total} fall through", c5))

    # 6 - agent guardrails
    # Whitespace-tolerant: the README is hard-wrapped, so the phrase this
    # reads may have a newline anywhere in it. A rubric that fails because a
    # paragraph reflowed teaches people to stop running the rubric.
    (want_agent,) = claim("agent guardrail tests", text,
                          "an agent-test count")

    def c6() -> Outcome:
        code, out = shell("-m", "pytest", "tests/test_agents.py",
                          "tests/test_agent_limits.py", "-q")
        stop = broken(code, out)
        if stop:
            return stop
        got = number(out, r"(\d+)\s+passed")
        failed = number(out, r"(\d+)\s+failed") or 0
        if got is None:
            return Outcome(False, "no result line", out.strip()[-400:])
        if failed:
            return Outcome(False, f"{got} passed, {failed} FAILED", out.strip()[-600:])
        if got < want_agent:
            return Outcome(False, f"{got} guardrail tests, the claims table states {want_agent}")
        drift = f"  (the claims table states {want_agent})" if got != want_agent else ""
        return Outcome(code == 0, f"{got} guardrail tests pass{drift}")

    crits.append(Criterion(6, "Agent guardrails", f"{want_agent} tests", c6))

    # 7 - paper the bundle never contained
    (want_cases,) = claim("unseen cases", text, "an unseen-case count")
    (want_read,) = claim("unseen fields read", text, "an unseen coverage count")
    (want_invented,) = claim("unseen defects invented", text, "an invented count")
    (want_waved,) = claim("unseen defects waved through", text, "a waved-through count")

    def c7() -> Outcome:
        code, out = shell("eval/unseen.py")
        stop = broken(code, out)
        if stop:
            return stop
        read = number(out, r"vocabulary read\s*:\s*(\d+)/")
        total = number(out, r"vocabulary read\s*:\s*\d+/(\d+)")
        cases = number(out, r"across (\d+) unfamiliar cases")
        invented = number(out, r"defects invented\s*:\s*(\d+)")
        waved = number(out, r"defects waved through\s*:\s*(\d+)")
        if None in (read, cases, invented, waved):
            return Outcome(False, "could not read the summary", out.strip()[-400:])

        bad = []
        # Judging a field wrongly is the failure. Reading less of an unfamiliar
        # document is a coverage limit, and only a drop below what is claimed
        # counts against it - improving coverage must never fail the check.
        if invented:
            bad.append(f"{invented} defect(s) invented")
        if waved:
            bad.append(f"{waved} defect(s) waved through")
        if cases < want_cases:
            bad.append(f"only {cases} cases (claimed {want_cases})")
        if read < want_read:
            bad.append(f"read {read} fields, claimed {want_read}")

        drift = f"  (claimed {want_read})" if read != want_read else ""
        return Outcome(
            not bad and code == 0,
            f"{read}/{total} fields read across {cases} cases, "
            f"{invented} invented, {waved} waved{drift}",
            "; ".join(bad),
        )

    crits.append(Criterion(7, "Unseen documents",
                           f"{want_cases} cases, {want_read} fields read, "
                           f"{want_invented} invented, {want_waved} waved", c7))

    # 8 - the grouping, tested against the code that ships
    (want_group,) = claim("grouping tests", text, "a grouping-test count")

    def c8() -> Outcome:
        npm = shutil.which("npm")
        if npm is None:
            return Outcome(False, "npm not found - the grouping is untested")
        try:
            p = subprocess.run([npm, "test", "--prefix", "web"], cwd=ROOT,
                               timeout=TIMEOUT, capture_output=True, text=True,
                               encoding="utf-8", errors="replace", shell=False)
        except subprocess.TimeoutExpired:
            return Outcome(False, f"TIMED OUT after {TIMEOUT}s")
        except OSError as exc:
            return Outcome(False, "COULD NOT START", str(exc)[:200])
        out = (p.stdout or "") + (p.stderr or "")
        got = number(out, r"^\D*pass (\d+)")
        failed = number(out, r"^\D*fail (\d+)") or 0
        if got is None:
            return Outcome(False, "no result line", out.strip()[-400:])
        if failed:
            return Outcome(False, f"{got} passed, {failed} FAILED",
                           out.strip()[-800:])
        if got < want_group:
            return Outcome(False, f"{got} grouping tests, the claims table "
                                  f"states {want_group}")
        drift = f"  (the claims table states {want_group})" if got != want_group else ""
        return Outcome(p.returncode == 0, f"{got} grouping tests pass{drift}")

    crits.append(Criterion(8, "Grouping", f"{want_group} tests", c8))
    return crits


# ---------------------------------------------------------------- reporting

def report(crits: list[Criterion], it: int, elapsed: float) -> bool:
    print(f"\n{'=' * 74}")
    print(f"RUBRIC - iteration {it}   ({elapsed:.0f}s)")
    print("=" * 74)
    for c in crits:
        o = c.last
        mark = "PASS" if o and o.ok else "FAIL"
        print(f"  [{mark}] {c.num}. {c.name:<22} {o.detail if o else '-'}")
        print(f"         claims: {c.quote}")
        if o and not o.ok and o.error:
            for line in o.error.strip().splitlines()[-6:]:
                print(f"         | {line}")
    failed = [c for c in crits if not (c.last and c.last.ok)]
    print("-" * 74)
    print(f"  {len(crits) - len(failed)}/{len(crits)} criteria pass")
    if failed:
        print("\n  Next: " + "; ".join(f"{c.num} {c.name}" for c in failed))
    return not failed


def signature(crits: list[Criterion]) -> tuple:
    """What changed between iterations - used to spot a stuck loop."""
    return tuple((c.num, c.last.ok, c.last.detail) if c.last else (c.num, None, "")
                 for c in crits)


def main() -> int:
    # Node's test reporter writes tick and info glyphs, and a Windows console
    # is cp1252. Printing a failure's output must not itself fail.
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(errors="replace")
        except (AttributeError, OSError):
            pass

    ap = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--loop", action="store_true",
                    help="re-run until every criterion passes")
    ap.add_argument("--max-iterations", type=int, default=10)
    ap.add_argument("--only", type=int, nargs="*", metavar="N",
                    help="check just these criteria")
    args = ap.parse_args()

    try:
        crits = build(readme_text())
    except RubricError as exc:
        print(f"cannot build the rubric: {exc}")
        return 2
    if args.only:
        crits = [c for c in crits if c.num in args.only]
        if not crits:
            print(f"no criteria numbered {args.only}")
            return 2

    seen: list[tuple] = []
    for it in range(1, (args.max_iterations if args.loop else 1) + 1):
        t = time.time()
        for c in crits:
            try:
                c.last = c.run()
            except Exception as exc:              # a broken check is a failure
                c.last = Outcome(False, "check itself errored",
                                 f"{type(exc).__name__}: {exc}")
        if report(crits, it, time.time() - t):
            print("\n  ALL CRITERIA PASS\n")
            return 0
        if not args.loop:
            return 1

        sig = signature(crits)
        if sig in seen:
            print("\n  STUCK: this iteration produced exactly the results an\n"
                  "  earlier one did. Running again cannot change anything -\n"
                  "  the failures above need a code change, not another pass.\n")
            return 1
        seen.append(sig)
        print(f"\n  ...re-running (iteration {it + 1})\n")

    print(f"\n  gave up after {args.max_iterations} iterations\n")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
