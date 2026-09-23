import test from "node:test";
import assert from "node:assert/strict";
import { getModeBadge } from "../src/supervisor.js";

test("only live mode claims LIVE LLM", () => {
  assert.deepEqual(getModeBadge("live"), { text: "LIVE LLM", variant: "success" });
  assert.equal(getModeBadge("scaffold").text, "SCAFFOLD MODE");
  for (const mode of [undefined, null, "", "unexpected"]) {
    assert.deepEqual(getModeBadge(mode), { text: "UNKNOWN MODE", variant: "muted" });
  }
});

test("dataset samples and replay are explicitly marked as no API", () => {
  assert.equal(getModeBadge("dataset_sample").text, "DEMO / NO API");
  assert.equal(getModeBadge("replay").text, "REPLAY / NO API");
});
