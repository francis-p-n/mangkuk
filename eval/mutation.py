#!/usr/bin/env python3
"""Defect injection — measure detection without ground truth.

We have no labels. But we do have pairs the pipeline calls clean, and we know
what a real defect looks like, because the corpus is full of them. So: take
every clean pair, inject one known defect into the draft BL, and check that the
pipeline reports exactly that field and nothing else.

Two numbers come out of this:
  recall    — injected defects that were caught
  precision — caught defects that were the injected one (no collateral flags)
Plus a control run with no mutation, which must stay silent.
"""
from __future__ import annotations

import collections
import json
import sys
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from sdoc.compare import compare_fieldsets                      # noqa: E402
from sdoc.documents import extract                              # noqa: E402
from sdoc.fields import FIELDS, extract_fields                  # noqa: E402
from sdoc.mailsource import BundleMailSource                    # noqa: E402
from sdoc.pipeline import run                                   # noqa: E402

# Realistic substitutions drawn from the corpus itself.
MUTATIONS: dict[str, list[tuple[str, object]]] = {
    "shipper":           [("different company", lambda v: "CLIFFORD PAPER INC")],
    "consignee":         [("different company", lambda v: "TOPKOPY MIDDLE EAST FZE")],
    "notify_party":      [("different company", lambda v: "NAGAPPA EXPORTS")],
    "port_of_loading":   [("different port", lambda v: "BUSAN, SOUTH KOREA (KRPUS)"),
                          ("wrong locode only", lambda v: _swap_locode(v))],
    "port_of_discharge": [("different port", lambda v: "CEBU, PHILIPPINES (PHCEB)"),
                          ("wrong locode only", lambda v: _swap_locode(v))],
    "container_count":   [("count off by one", lambda v: _bump_count(v)),
                          ("wrong box type", lambda v: v.replace("40", "20") if "40" in v else v.replace("20", "40"))],
    "gross_weight_kg":   [("weight off by 2000", lambda v: _bump_weight(v))],
}


def _swap_locode(value: str) -> str:
    import re
    return re.sub(r"\(([A-Z]{5})\)", lambda m: "(ZZZZZ)" if m.group(1) != "ZZZZZ" else "(YYYYY)", value)


def _bump_count(value: str) -> str:
    import re
    return re.sub(r"^(\s*)(\d+)", lambda m: f"{m.group(1)}{int(m.group(2)) + 1}", value)


def _bump_weight(value: str) -> str:
    import re
    m = re.search(r"([\d,]+)", value)
    if not m:
        return value
    bumped = f"{int(m.group(1).replace(',', '')) + 2000:,}"
    return value.replace(m.group(1), bumped, 1)


def rewrite_field(text: str, line_no: int, new_value: str) -> str:
    lines = text.splitlines()
    label, sep, _ = lines[line_no - 1].partition(":")
    lines[line_no - 1] = f"{label}{sep} {new_value}"
    return "\n".join(lines)


@dataclass
class Outcome:
    field: str
    strategy: str
    caught: bool
    exact: bool
    reported: tuple[str, ...]


def main() -> int:
    src = BundleMailSource(ROOT / "data")
    clean = [r for r in run(src) if r.category == "BL_COMPARISON" and r.status == "OK"]
    print(f"clean pairs available as mutation hosts: {len(clean)}\n")

    outcomes: list[Outcome] = []
    control_failures = 0

    for result in clean:
        si_path = next(d["path"] for d in result.documents if d["role"] == "SI")
        bl_path = next(d["path"] for d in result.documents if d["role"] == "BL")
        si_text = extract(src, si_path).text
        bl_text = extract(src, bl_path).text
        si_fields = extract_fields(si_text)
        bl_fields = extract_fields(bl_text)

        # Control: unmutated pairs must stay OK.
        if compare_fieldsets(si_fields, extract_fields(bl_text)).status != "OK":
            control_failures += 1

        for name in FIELDS:
            target = bl_fields.get(name)
            if target is None:
                continue
            for strategy, mutate in MUTATIONS[name]:
                new_value = mutate(target.value)
                if new_value == target.value:
                    continue
                mutated = rewrite_field(bl_text, target.line_no, new_value)
                verdict = compare_fieldsets(si_fields, extract_fields(mutated))
                reported = tuple(verdict.defect_fields)
                outcomes.append(Outcome(
                    field=name,
                    strategy=strategy,
                    caught=name in reported,
                    exact=reported == (name,),
                    reported=reported,
                ))

    total = len(outcomes)
    caught = sum(o.caught for o in outcomes)
    exact = sum(o.exact for o in outcomes)
    print(f"injected defects : {total}")
    print(f"caught           : {caught}  ({caught / total:.1%})")
    print(f"caught cleanly   : {exact}  ({exact / total:.1%} - no collateral fields)")
    print(f"control failures : {control_failures}  (unmutated pairs that stopped being OK)\n")

    by_field = collections.defaultdict(lambda: [0, 0])
    for o in outcomes:
        by_field[f"{o.field} / {o.strategy}"][0] += o.caught
        by_field[f"{o.field} / {o.strategy}"][1] += 1
    print(f"{'field / injected defect':<44} {'caught':>10}")
    for key in sorted(by_field):
        hit, n = by_field[key]
        flag = "" if hit == n else "   <-- MISSED"
        print(f"  {key:<42} {hit:>4}/{n:<4}{flag}")

    misses = [o for o in outcomes if not o.caught]
    if misses:
        print(f"\n{len(misses)} missed injection(s):")
        for o in misses[:10]:
            print(f"  {o.field} via {o.strategy} -> reported {o.reported or '(nothing)'}")

    (ROOT / "out").mkdir(exist_ok=True)
    (ROOT / "out" / "mutation_report.json").write_text(json.dumps({
        "hosts": len(clean), "injected": total, "caught": caught, "exact": exact,
        "control_failures": control_failures,
        "by_strategy": {k: {"caught": v[0], "total": v[1]} for k, v in sorted(by_field.items())},
    }, indent=2), encoding="utf-8")
    return 0 if (caught == total and control_failures == 0) else 1


if __name__ == "__main__":
    raise SystemExit(main())
