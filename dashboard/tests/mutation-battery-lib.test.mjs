import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

// Loaded as TypeScript through Node's type stripping; see the `test` script.
import {
  groupCasesByFile,
  mutationCounts,
  parseMutationSummary,
} from "../app/lib/mutation-battery.ts";

const summaryUrl = new URL("../../badges/mutation-battery-summary.json", import.meta.url);
const badgeUrl = new URL("../../badges/mutation-battery.svg", import.meta.url);

// Every expected value below is derived from the committed file, never typed:
// a fixture that restated "39" would keep passing after the battery changed.
const committedText = await readFile(summaryUrl, "utf8");
const committed = JSON.parse(committedText);

function summaryWith(change) {
  const copy = structuredClone(committed);
  change(copy);
  return JSON.stringify(copy);
}

test("the committed summary parses, and its headline is its own arithmetic", () => {
  const summary = parseMutationSummary(committedText);
  assert.equal(summary.cases.length, committed.cases.length);
  assert.equal(summary.total, summary.cases.length);
  assert.equal(summary.caught, summary.cases.filter((c) => c.status === "caught").length);
  assert.deepEqual(mutationCounts(summary), { total: summary.total, caught: summary.caught });
});

test("the badge and the summary come from one CI run and say the same count", async () => {
  // lab/render-badge.py writes "<label>: <caught>/<total>" into the badge's
  // aria-label from this same summary; the publish job commits both together.
  const badge = await readFile(badgeUrl, "utf8");
  const label = /aria-label="([^"]*)"/.exec(badge)?.[1];
  assert.equal(label, `injected violations caught: ${committed.caught}/${committed.total}`);
});

test("a summary that disagrees with its own cases is rejected, not displayed", () => {
  assert.throws(
    () => parseMutationSummary(summaryWith((s) => { s.total += 1; })),
    /total is \d+ but the file lists \d+ cases/,
  );
  assert.throws(
    () => parseMutationSummary(summaryWith((s) => { s.cases = s.cases.slice(1); })),
    /total is \d+ but the file lists \d+ cases/,
    "a truncated case list must not pass as a smaller battery",
  );
  assert.throws(
    () => parseMutationSummary(summaryWith((s) => { s.cases[0].status = "missed"; })),
    /caught is \d+ but \d+ cases are caught/,
    "a case flipped to missed must not leave the headline claiming a full catch",
  );
  assert.throws(
    () => parseMutationSummary(summaryWith((s) => { s.missed += 1; })),
    /missed is \d+, expected \d+/,
  );
});

test("malformed entries are rejected with the field that is wrong", () => {
  assert.throws(() => parseMutationSummary("not json"), /is not valid JSON/);
  assert.throws(() => parseMutationSummary("[]"), /must be a JSON object/);
  assert.throws(
    () => parseMutationSummary(summaryWith((s) => { s.cases[0].status = "passed"; })),
    /cases\[0\]\.status "passed" is not one of/,
  );
  assert.throws(
    () => parseMutationSummary(summaryWith((s) => { delete s.cases[0].test_file; })),
    /cases\[0\]\.test_file must be a non-empty string/,
  );
  assert.throws(
    () => parseMutationSummary(summaryWith((s) => { s.cases[1].name = s.cases[0].name; })),
    /appears twice/,
  );
  assert.throws(
    () => parseMutationSummary(summaryWith((s) => { s.generated_at = "yesterday"; })),
    /not a UTC timestamp/,
  );
});

test("a case the suite did not catch keeps its own status and is counted out", () => {
  const summary = parseMutationSummary(
    summaryWith((s) => {
      s.cases[0].status = "missed";
      s.cases[0].matched_test = null;
      s.caught -= 1;
      s.missed += 1;
    }),
  );
  assert.equal(summary.total - summary.caught, 1);
  assert.equal(summary.cases[0].status, "missed");
  assert.equal(summary.cases[0].matchedTest, null);
});

test("grouping keeps every case exactly once, under the file that guards it", () => {
  const { cases } = parseMutationSummary(committedText);
  const groups = groupCasesByFile(cases);

  assert.equal(
    groups.reduce((sum, group) => sum + group.cases.length, 0),
    cases.length,
    "no case may be dropped or duplicated by grouping",
  );
  assert.deepEqual(
    groups.map((g) => g.file),
    [...new Set(cases.map((c) => c.testFile))].sort((a, b) => a.localeCompare(b)),
    "one group per distinct file, in path order",
  );
  for (const group of groups) {
    assert.ok(group.cases.every((c) => c.testFile === group.file));
    assert.equal(group.caught, group.cases.filter((c) => c.status === "caught").length);
  }
  // Cases keep the battery's order inside a group.
  for (const group of groups) {
    const expected = cases.filter((c) => c.testFile === group.file).map((c) => c.name);
    assert.deepEqual(group.cases.map((c) => c.name), expected);
  }
});

test("a file holding a case the suite did not catch is listed first", () => {
  const { cases } = parseMutationSummary(committedText);
  // Break a case in the file that sorts last, so path order alone would bury it.
  const lastFile = groupCasesByFile(cases).at(-1).file;
  const broken = cases.map((c, index) =>
    index === cases.findIndex((x) => x.testFile === lastFile)
      ? { ...c, status: "missed", matchedTest: null }
      : c,
  );
  const groups = groupCasesByFile(broken);
  assert.equal(groups[0].file, lastFile, "the failing file leads");
  assert.notEqual(groups[0].caught, groups[0].cases.length);
  // Everything after it is in path order again.
  const rest = groups.slice(1).map((g) => g.file);
  assert.deepEqual(rest, [...rest].sort((a, b) => a.localeCompare(b)));
  assert.equal(groups.reduce((sum, g) => sum + g.cases.length, 0), cases.length);
});
