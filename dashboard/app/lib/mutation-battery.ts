// Pure, no I/O: the client takes types and labels from here, the server reads
// the committed summary through ./mutation-battery-source, and the node tests
// import this file directly under --experimental-strip-types.
//
// The summary is badges/mutation-battery-summary.json, written by
// lab/summarize-mutation-results.py from the safety workflow's shard logs and
// committed beside badges/mutation-battery.svg. Nothing here restates a count
// or a case: everything the page shows is parsed from that file, and a file
// whose numbers disagree with its own cases is rejected rather than shown.

// The statuses lab/summarize-mutation-results.py can write. Only "caught" is a
// pass; the others are distinct ways the battery can fail and stay distinct so
// a reader can tell a suite that stayed green from a harness that broke.
export const CASE_STATUSES = ["caught", "missed", "wrong", "error", "not_run"] as const;
export type CaseStatus = (typeof CASE_STATUSES)[number];

export const VERDICT_LABEL: Record<CaseStatus, string> = {
  caught: "Caught",
  missed: "Missed",
  wrong: "Failed the wrong test",
  error: "Harness error",
  not_run: "Not run",
};

// What each non-pass status means, as lab/verify-safety-suite.sh reports it.
// Shown beside the test the case was expected to fail.
export const NOT_CAUGHT_DETAIL: Record<Exclude<CaseStatus, "caught">, string> = {
  missed: "The suite stayed green.",
  wrong: "The suite failed, but not on the expected test.",
  error: "The harness failed before it reached a verdict.",
  not_run: "No result was recorded for this case.",
};

export type MutationCase = {
  name: string;
  expectedTest: string;
  testFile: string;
  status: CaseStatus;
  matchedTest: string | null;
};

export type MutationSummary = {
  generatedAt: string;
  total: number;
  caught: number;
  cases: MutationCase[];
};

export type MutationCounts = { total: number; caught: number };

export type MutationGroup = {
  file: string;
  cases: MutationCase[];
  caught: number;
};

function fail(message: string): never {
  throw new Error(`mutation-battery-summary.json: ${message}`);
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function requireString(record: Record<string, unknown>, key: string, where: string): string {
  const value = record[key];
  if (typeof value !== "string" || value === "") fail(`${where}.${key} must be a non-empty string`);
  return value;
}

function requireCount(record: Record<string, unknown>, key: string): number {
  const value = record[key];
  if (typeof value !== "number" || !Number.isInteger(value) || value < 0) {
    fail(`${key} must be a non-negative integer`);
  }
  return value;
}

export function parseMutationSummary(text: string): MutationSummary {
  let raw: unknown;
  try {
    raw = JSON.parse(text);
  } catch {
    fail("is not valid JSON");
  }
  if (!isRecord(raw)) fail("must be a JSON object");

  const generatedAt = requireString(raw, "generated_at", "summary");
  if (!/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$/.test(generatedAt)) {
    fail(`generated_at ${JSON.stringify(generatedAt)} is not a UTC timestamp`);
  }
  const total = requireCount(raw, "total");
  const caught = requireCount(raw, "caught");
  const missed = requireCount(raw, "missed");
  if (!Array.isArray(raw.cases)) fail("cases must be an array");

  const seen = new Set<string>();
  const cases = raw.cases.map((entry: unknown, index: number): MutationCase => {
    const where = `cases[${index}]`;
    if (!isRecord(entry)) fail(`${where} must be an object`);
    const name = requireString(entry, "name", where);
    if (seen.has(name)) fail(`${where}: the case name ${JSON.stringify(name)} appears twice`);
    seen.add(name);
    const status = requireString(entry, "status", where);
    if (!(CASE_STATUSES as readonly string[]).includes(status)) {
      fail(`${where}.status ${JSON.stringify(status)} is not one of ${CASE_STATUSES.join(", ")}`);
    }
    const matched = entry.matched_test;
    if (matched !== null && typeof matched !== "string") {
      fail(`${where}.matched_test must be a string or null`);
    }
    return {
      name,
      expectedTest: requireString(entry, "expected_test", where),
      testFile: requireString(entry, "test_file", where),
      status: status as CaseStatus,
      matchedTest: matched,
    };
  });

  // The headline is read off these three numbers, so they must be the cases'
  // own arithmetic: a summary edited by hand, or truncated, fails here.
  const actuallyCaught = cases.filter((c) => c.status === "caught").length;
  if (total !== cases.length) fail(`total is ${total} but the file lists ${cases.length} cases`);
  if (caught !== actuallyCaught) fail(`caught is ${caught} but ${actuallyCaught} cases are caught`);
  if (missed !== total - caught) fail(`missed is ${missed}, expected ${total - caught}`);

  return { generatedAt, total, caught, cases };
}

export function mutationCounts(summary: MutationSummary): MutationCounts {
  return { total: summary.total, caught: summary.caught };
}

// One group per test file, cases in battery order. The file is the one the
// summarizer resolved from the case's expected test. Files are in path order,
// except that a file holding a case the suite did not catch comes first: when
// the battery fails, the reader should not have to hunt for where.
export function groupCasesByFile(cases: MutationCase[]): MutationGroup[] {
  const byFile = new Map<string, MutationCase[]>();
  for (const entry of cases) {
    const group = byFile.get(entry.testFile);
    if (group) group.push(entry);
    else byFile.set(entry.testFile, [entry]);
  }
  return [...byFile.entries()]
    .map(([file, group]) => ({
      file,
      cases: group,
      caught: group.filter((c) => c.status === "caught").length,
    }))
    .sort(
      (a, b) =>
        Number(a.caught === a.cases.length) - Number(b.caught === b.cases.length) ||
        a.file.localeCompare(b.file),
    );
}
