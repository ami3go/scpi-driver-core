"""Generate RFDS-019 evidence summaries from an N6775A Robot self-check run."""
from __future__ import annotations

import argparse
import csv
import json
import shutil
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "tests/conformance/data"


def load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def test_results(output_xml: Path) -> dict[str, dict[str, str]]:
    if not output_xml.is_file():
        return {}
    root = ET.parse(output_xml).getroot()
    results: dict[str, dict[str, str]] = {}
    for test in root.iter("test"):
        name = test.get("name", "")
        status = test.find("status")
        number = name.split(" ", 1)[0].lstrip("0") or "0"
        results[number] = {
            "name": name,
            "status": status.get("status", "NOT RUN") if status is not None else "NOT RUN",
            "message": (status.text or "") if status is not None else "",
        }
    return results


def status_for_refs(refs: str, tests: dict[str, dict[str, str]]) -> str:
    statuses: list[str] = []
    for ref in (part.strip() for part in refs.split(",")):
        if ref == "setup":
            continue
        key = ref.lstrip("0") or "0"
        statuses.append(tests.get(key, {}).get("status", "NOT RUN"))
    if not statuses:
        return "PASS" if tests else "NOT RUN"
    if "FAIL" in statuses:
        return "FAIL"
    if "NOT RUN" in statuses:
        return "NOT RUN"
    if all(value == "SKIP" for value in statuses):
        return "SKIP"
    if "SKIP" in statuses:
        return "SKIP"
    return "PASS"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output_dir", type=Path)
    args = parser.parse_args()
    out = args.output_dir.resolve()
    out.mkdir(parents=True, exist_ok=True)

    inventory_doc = load(DATA / "keyword_inventory.yaml")
    vectors_doc = load(DATA / "protocol_vectors.yaml")
    exclusions_doc = load(DATA / "exclusions.yaml")
    inventory = inventory_doc["inventory"]
    vectors = vectors_doc["vectors"]
    exclusions = exclusions_doc["exclusions"]
    tests = test_results(out / "output.xml")
    vector_by_keyword = {item["keyword"]: item for item in vectors}
    exclusion_by_keyword = {item["keyword"]: item for item in exclusions}

    (out / "keyword_inventory.json").write_text(json.dumps(inventory_doc, indent=2) + "\n", encoding="utf-8")
    (out / "exclusions.json").write_text(json.dumps(exclusions_doc, indent=2) + "\n", encoding="utf-8")

    vector_results = []
    for vector in vectors:
        result = dict(vector)
        result["result"] = status_for_refs(str(vector.get("test_case", "")), tests)
        result["evidence"] = "protocol_trace.jsonl"
        vector_results.append(result)
    (out / "protocol_vector_results.json").write_text(
        json.dumps({"module_profile": "N6775A", "vectors": vector_results}, indent=2) + "\n",
        encoding="utf-8",
    )

    rows: list[dict[str, str]] = []
    for item in inventory:
        keyword = item["public_keyword"]
        vector = vector_by_keyword.get(keyword)
        exclusion = exclusion_by_keyword.get(keyword)
        refs = str(vector.get("test_case", "")) if vector else "16" if exclusion and "expected UnsupportedFeatureError" in exclusion.get("verification", "") else ""
        result = status_for_refs(refs, tests) if vector else "EXCLUDED"
        if exclusion and refs:
            result = status_for_refs(refs, tests)
        rows.append({
            "Keyword name": keyword,
            "Canonical keyword": item.get("canonical_keyword", keyword),
            "Driver method": item.get("driver_method", ""),
            "Device-facing": str(item.get("device_facing", False)),
            "Transport type": (vector or {}).get("expected_outbound", {}).get("transport", "N/A"),
            "Protocol vector": (vector or {}).get("id", ""),
            "Callability tested": "Yes" if vector or refs else "No",
            "Outbound verified": "PASS" if vector and result == "PASS" else "N/A" if not vector else result,
            "Raw response verified": "PASS" if vector and result == "PASS" and vector.get("expected_inbound", {}).get("response_required") else "N/A",
            "Parsed result verified": "PASS" if vector and result == "PASS" else "N/A" if not vector else result,
            "Protocol error tested": "PASS" if keyword in {"Write N6700 SCPI", "Query N6700 SCPI", "Drain N6700 Errors", "Check N6700 Errors"} and tests.get("14", {}).get("status") == "PASS" else "N/A",
            "Recovery tested": "PASS" if tests.get("14", {}).get("status") == "PASS" and keyword in {"Query N6700 SCPI", "Get N6700 Identity"} else "N/A",
            "Result": result,
            "Evidence": "protocol_trace.jsonl" if vector else "tests/conformance/data/exclusions.yaml",
            "Reason": (exclusion or {}).get("reason", ""),
        })
    with (out / "keyword_coverage.csv").open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)

    trace = out / "protocol_trace.jsonl"
    outbound: list[str] = []
    inbound: list[str] = []
    if trace.is_file():
        for line in trace.read_text(encoding="utf-8").splitlines():
            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                continue
            outbound.append(json.dumps(record, sort_keys=True))
            if record.get("operation") == "query":
                inbound.append(json.dumps(record, sort_keys=True))
    (out / "outbound_trace.log").write_text("\n".join(outbound) + ("\n" if outbound else ""), encoding="utf-8")
    (out / "inbound_trace.log").write_text("\n".join(inbound) + ("\n" if inbound else ""), encoding="utf-8")

    counts: dict[str, int] = {}
    for value in tests.values():
        counts[value["status"]] = counts.get(value["status"], 0) + 1
    vector_counts: dict[str, int] = {}
    for item in vector_results:
        vector_counts[item["result"]] = vector_counts.get(item["result"], 0) + 1
    summary = [
        "# N6775A RFDS-019 self-check summary",
        "",
        f"- Public keyword inventory: **{len(inventory)}/{inventory_doc['public_keyword_count']}**",
        f"- Protocol vectors: **{len(vectors)}**",
        f"- Approved exclusions: **{len(exclusions)}**",
        f"- Robot test results: **{counts}**",
        f"- Protocol vector results: **{vector_counts}**",
        f"- Protocol trace records: **{len(outbound)}**",
        "",
        "The active-output and reset vectors are SKIP unless explicitly enabled. Hardware PASS status requires a real N6700 mainframe with an N6775A in the selected channel.",
    ]
    (out / "conformance_summary.md").write_text("\n".join(summary) + "\n", encoding="utf-8")
    if (out / "protocol_trace.jsonl").is_file() and not (out / "protocol_trace.log").exists():
        shutil.copy2(out / "protocol_trace.jsonl", out / "protocol_trace.log")
    print(f"Generated RFDS-019 evidence in {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
