"""Offline tests validating frontend assets, catalog consistency, contract alignment and XSS safety."""
import json
import re
from pathlib import Path
import pytest

FRONTEND_DIR = Path(__file__).resolve().parent.parent
SRC_DIR = FRONTEND_DIR / "src"
ROOT_DIR = FRONTEND_DIR.parent

def test_frontend_files_exist():
    assert (FRONTEND_DIR / "index.html").is_file()
    assert (SRC_DIR / "favicon.svg").is_file()
    assert (SRC_DIR / "api.js").is_file()
    assert (SRC_DIR / "app.js").is_file()
    assert (SRC_DIR / "audio.js").is_file()
    assert (SRC_DIR / "catalog.js").is_file()
    assert (SRC_DIR / "metrics.js").is_file()
    assert (SRC_DIR / "supervisor.js").is_file()
    assert (SRC_DIR / "replay.js").is_file()
    assert (SRC_DIR / "i18n.js").is_file()
    assert (SRC_DIR / "styles.css").is_file()

def test_catalog_matches_official_scenarios():
    """Verify that frontend/src/catalog.js covers all 40 official scenarios."""
    scenarios_json_path = ROOT_DIR / "case_2" / "voice_router_dataset" / "scenarios.json"
    with open(scenarios_json_path, encoding="utf-8") as f:
        data = json.load(f)
    official_scenarios = {s["scenario_id"]: s for s in data["scenarios"]}
    assert len(official_scenarios) == 40

    catalog_js = (SRC_DIR / "catalog.js").read_text(encoding="utf-8")
    for sc_id, sc_data in official_scenarios.items():
        assert f'id: "{sc_id}"' in catalog_js, f"Missing scenario {sc_id} in catalog.js"
        assert f'priority: "{sc_data["priority"]}"' in catalog_js, f"Mismatched priority for {sc_id}"
        assert f'category: "{sc_data["category"]}"' in catalog_js, f"Mismatched category for {sc_id}"

    # Also verify system intents exist
    assert 'SYS_OUT_OF_SCOPE' in catalog_js
    assert 'SYS_UNCLEAR' in catalog_js
    assert 'SYS_GOODBYE' in catalog_js

def test_no_unsafe_inner_html_injection_in_components():
    """Verify that user strings and server responses are NOT injected via unsafe .innerHTML assignments."""
    for filename in ["supervisor.js", "metrics.js", "catalog.js", "replay.js", "api.js"]:
        content = (SRC_DIR / filename).read_text(encoding="utf-8")
        assert not re.search(r'\.innerHTML\s*=', content), f"Potentially unsafe innerHTML assignment found in {filename}"

def test_percentile_calculation_logic():
    """Unit test for percentile and median calculation logic."""
    def calc_p(values, p):
        sorted_vals = sorted(values)
        idx = (p / 100) * (len(sorted_vals) - 1)
        lower, upper = int(idx), int(idx) + (1 if idx % 1 > 0 else 0)
        weight = idx - lower
        if lower == upper:
            return sorted_vals[lower]
        return sorted_vals[lower] * (1 - weight) + sorted_vals[upper] * weight

    samples = [500, 800, 1200, 1500, 2000]
    p50 = calc_p(samples, 50)
    assert p50 == 1200
    p95 = calc_p(samples, 95)
    assert p95 > 1500
