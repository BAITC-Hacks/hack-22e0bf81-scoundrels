from backend.router.evals.performance import quality_exit_code, summarize


def row(**changes):
    return dict(profile="baseline", warmup=False, expected=["SC25"], predicted=["SC25"],
                expected_language="ru", language="ru", latency_ms=100, output_tokens=20) | changes


def test_quality_gate_rejects_wrong_route_language_errors_and_empty_run():
    assert quality_exit_code([row()]) == 0
    assert quality_exit_code([row(predicted=["SC26"])]) == 1
    assert quality_exit_code([row(language="mixed")]) == 1
    assert quality_exit_code([row(error="RouterProviderError")]) == 2
    assert quality_exit_code([]) == 1
    assert quality_exit_code([row(warmup=True)]) == 1


def test_summary_excludes_warmup_and_does_not_hide_errors_from_quality():
    records = [row(warmup=True, latency_ms=9000), row(),
               row(predicted=None, language=None, error="TimeoutError", latency_ms=12000)]
    result = summarize(records)["baseline"]
    assert result["count"] == 2
    assert result["api_errors"] == 1
    assert result["ordered_correct"] == 1
    assert result["language_correct"] == 1
    assert result["p50_ms"] == 100
    assert result["mean_output_tokens"] == 20
