import assert from "node:assert/strict";
import test from "node:test";

import { analyzeDraft, splitClaims } from "./engine.mjs";

const sources = [
  {
    title: "Archive note",
    url: "https://example.org/archive",
    text: "Hampi served as the capital of the Vijayanagara Empire from the fourteenth century. The archaeological area contains more than 1,600 surviving remains.",
  },
  {
    title: "Monument note",
    url: "https://example.org/monument",
    text: "The Stone Chariot stands inside the Vittala Temple complex. The structure is a shrine designed in the form of a ceremonial chariot.",
  },
];

test("splits sentences and semicolon-separated claims", () => {
  assert.deepEqual(splitClaims("One claim is here; another claim follows. Final claim."), [
    "One claim is here",
    "another claim follows.",
    "Final claim.",
  ]);
});

test("supports a claim with matching evidence", () => {
  const result = analyzeDraft(
    "Hampi served as the capital of the Vijayanagara Empire.",
    sources,
  );
  assert.equal(result.claims[0].status, "supported");
  assert.equal(result.publishGate, "pass");
});

test("flags an unsupported date even with strong surrounding overlap", () => {
  const result = analyzeDraft(
    "The Stone Chariot was built in 1565 inside the Vittala Temple complex.",
    sources,
  );
  assert.notEqual(result.claims[0].status, "supported");
  assert.deepEqual(result.claims[0].unsupportedNumbers, ["1565"]);
  assert.equal(result.publishGate, "hold");
});

test("returns the exact best evidence span", () => {
  const result = analyzeDraft(
    "The archaeological area contains more than 1,600 surviving remains.",
    sources,
  );
  assert.match(result.claims[0].evidence, /1,600 surviving remains/);
  assert.equal(result.claims[0].sourceTitle, "Archive note");
});

test("rejects analysis without usable sources", () => {
  assert.throws(
    () => analyzeDraft("A complete factual claim.", []),
    /source/i,
  );
});
