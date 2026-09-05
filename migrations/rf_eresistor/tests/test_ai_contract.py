import ast
import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _implemented_keywords():
    tree = ast.parse((ROOT / "rf_eresistor" / "library.py").read_text(encoding="utf-8"))
    names = []
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        for decorator in node.decorator_list:
            if (isinstance(decorator, ast.Call) and isinstance(decorator.func, ast.Name)
                    and decorator.func.id == "keyword" and decorator.args
                    and isinstance(decorator.args[0], ast.Constant)):
                names.append(decorator.args[0].value)
    return names


def test_contract_lock_and_keyword_coverage():
    raw = (ROOT / "ai" / "eresistor_ai_contract.yaml").read_bytes()
    contract = json.loads(raw)
    lock = json.loads((ROOT / "ai" / "eresistor_ai_contract.lock").read_text(encoding="utf-8"))
    documented = [item["keyword"] for item in contract["capabilities"]]
    implemented = _implemented_keywords()
    assert hashlib.sha256(raw).hexdigest() == lock["sha256"]
    assert lock["capability_count"] == len(documented)
    assert len(documented) == len(set(documented))
    assert set(documented) == set(implemented)


def test_every_capability_has_rfds_semantics():
    contract = json.loads((ROOT / "ai" / "eresistor_ai_contract.yaml").read_text(encoding="utf-8"))
    required = {"signature", "purpose", "inputs", "output", "preconditions",
                "postconditions", "side_effects", "risk_level", "timing",
                "stabilization_delay", "retry_policy", "errors", "exclusive_resources"}
    for capability in contract["capabilities"]:
        assert required <= capability.keys(), capability["keyword"]


def test_mandatory_top_level_sections_exist():
    contract = json.loads((ROOT / "ai" / "eresistor_ai_contract.yaml").read_text(encoding="utf-8"))
    required = {"identity", "mental_model", "state_machine", "resources", "dependencies",
                "capabilities", "error_catalogue", "safety_rules", "verification_objectives",
                "setup_teardown_contract", "limitations", "planning_hints", "unknown_handling",
                "conformance"}
    assert required <= contract.keys()
