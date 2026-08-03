"use client";

import {
  Activity,
  BadgeCheck,
  BarChart3,
  BookOpenCheck,
  Check,
  CheckCircle2,
  ChevronRight,
  CircleDot,
  CloudOff,
  Command,
  Copy,
  Cpu,
  Database,
  Download,
  FileCheck2,
  FileCode2,
  FileJson,
  FileSearch,
  Filter,
  Fingerprint,
  FlaskConical,
  Ghost,
  HardDrive,
  Info,
  KeyRound,
  Layers3,
  LayoutDashboard,
  ListChecks,
  LockKeyhole,
  Menu,
  Network,
  Play,
  Radio,
  RefreshCw,
  ScanLine,
  Search,
  Settings2,
  Shield,
  ShieldCheck,
  SquareTerminal,
  TestTube2,
  TriangleAlert,
  X,
  Zap,
} from "lucide-react";
import type { LucideIcon } from "lucide-react";
import {
  CartesianGrid,
  Legend,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { useEffect, useMemo, useState } from "react";

type View =
  | "overview"
  | "runs"
  | "probes"
  | "evidence"
  | "reports"
  | "providers"
  | "safety";

type NavItem = {
  id: View;
  label: string;
  icon: LucideIcon;
  hint: string;
};

type RunRecord = {
  id: string;
  label: string;
  timestamp: string;
  records: number;
  observations: number;
  path: string;
  control: string;
  integrity: "Internally consistent";
  trust: "Embedded key" | "External key";
  publication: "Eligible" | "Protected" | "Development only";
  type: "Real local" | "Simulated fixture" | "Native local";
  note: string;
};

type Probe = {
  section: string;
  name: string;
  code: string;
  state: "Local capable" | "Host blocked" | "Rental gated" | "Hardware gated";
  detail: string;
  executable: boolean;
};

type OperatorAction = {
  id: string;
  name: string;
  summary: string;
  command: string;
  tone: "safe" | "write" | "verify";
  icon: LucideIcon;
};

const navItems: NavItem[] = [
  {
    id: "overview",
    label: "Overview",
    icon: LayoutDashboard,
    hint: "Mission state and evidence health",
  },
  {
    id: "runs",
    label: "Runs",
    icon: Activity,
    hint: "Local batteries and execution plans",
  },
  {
    id: "probes",
    label: "Probe lab",
    icon: FlaskConical,
    hint: "Thirteen chartered probe families",
  },
  {
    id: "evidence",
    label: "Evidence",
    icon: Database,
    hint: "Signed bundles and measurement paths",
  },
  {
    id: "reports",
    label: "Report cards",
    icon: BarChart3,
    hint: "Independent assurance categories",
  },
  {
    id: "providers",
    label: "Providers",
    icon: Network,
    hint: "Policy readiness and permission gates",
  },
  {
    id: "safety",
    label: "Safety",
    icon: ShieldCheck,
    hint: "Canary-only invariants and release gates",
  },
];

const operatorActions: OperatorAction[] = [
  {
    id: "smoke",
    name: "Capability smoke",
    summary: "Read-only host and CUDA capability preflight.",
    command: "python lab/local-runner/smoke.py",
    tone: "safe",
    icon: ScanLine,
  },
  {
    id: "phase1",
    name: "Phase 1 controls",
    summary: "Global VRAM measurement plus framework positive control.",
    command:
      "python lab/local-runner/run_phase1.py --out ./out --size-mib 32 --cycles 10 --simulate",
    tone: "write",
    icon: TestTube2,
  },
  {
    id: "phase2",
    name: "Phase 2 rehearsal",
    summary: "Complete local battery and independent report card.",
    command:
      "python lab/local-runner/run_phase2_local.py --out ./out --size-mib 32 --cycles 10 --simulate",
    tone: "write",
    icon: Layers3,
  },
  {
    id: "safety",
    name: "Verify safety suite",
    summary: "Prove that all injected policy violations are rejected.",
    command: "bash lab/verify-safety-suite.sh",
    tone: "verify",
    icon: ShieldCheck,
  },
  {
    id: "policy",
    name: "Check provider policy",
    summary: "Evaluate the Phase 0 provider permission gate.",
    command: "python lab/check-provider-policy.py",
    tone: "safe",
    icon: BookOpenCheck,
  },
  {
    id: "release",
    name: "Check release readiness",
    summary: "Run the repository publication and provenance gates.",
    command: "python lab/check-release-readiness.py",
    tone: "verify",
    icon: FileCheck2,
  },
];

const probes: Probe[] = [
  {
    section: "§9.1",
    name: "Environment inventory",
    code: "environment_inventory",
    state: "Local capable",
    detail: "Tenant-visible OS, container, device and CUDA inventory.",
    executable: true,
  },
  {
    section: "§9.2",
    name: "Local/shared sanitisation",
    code: "local_memory_sanitisation",
    state: "Host blocked",
    detail: "Expected-negative shared-memory boundary test; CUDA required.",
    executable: true,
  },
  {
    section: "§9.3",
    name: "Device-global VRAM",
    code: "memory_global_read_before_write",
    state: "Host blocked",
    detail: "Driver-direct, read-before-write allocation measurement.",
    executable: true,
  },
  {
    section: "§9.4",
    name: "Framework allocator control",
    code: "framework_allocator_reuse",
    state: "Host blocked",
    detail: "Positive control. Canary recovery here means the instrument worked.",
    executable: true,
  },
  {
    section: "§9.5",
    name: "Sequential self-canary",
    code: "self_sequential_canary",
    state: "Rental gated",
    detail: "Requires two owned rentals and the §9.8b separability gate.",
    executable: true,
  },
  {
    section: "§9.6",
    name: "Device exposure",
    code: "device_exposure_inventory",
    state: "Host blocked",
    detail: "Passive device and namespace exposure classification.",
    executable: true,
  },
  {
    section: "§9.7",
    name: "Allocation model",
    code: "allocation_model_classifier",
    state: "Host blocked",
    detail: "Ranks tenancy hypotheses; confidence is not a probability.",
    executable: true,
  },
  {
    section: "§9.8",
    name: "Topology fingerprint",
    code: "topology_fingerprint",
    state: "Host blocked",
    detail: "Hardware-class consistency instrument reproduced on RTX silicon.",
    executable: true,
  },
  {
    section: "§9.8b",
    name: "Same-model separability",
    code: "separability_analysis",
    state: "Rental gated",
    detail: "Offline evaluator; needs N rented instances of one model.",
    executable: false,
  },
  {
    section: "§9.9",
    name: "Location consistency",
    code: "coarse_location_consistency",
    state: "Rental gated",
    detail: "Coarse jurisdiction consistency; never rack-level attribution.",
    executable: true,
  },
  {
    section: "§9.10",
    name: "Attestation assurance",
    code: "attestation_assurance",
    state: "Hardware gated",
    detail: "Ten independent availability and verification fields.",
    executable: true,
  },
  {
    section: "§9.11",
    name: "Channel binding",
    code: "assess_channel_binding",
    state: "Hardware gated",
    detail: "Shares the attestation experiment; controlled endpoints required.",
    executable: false,
  },
  {
    section: "§9.12",
    name: "MIG temporal isolation",
    code: "mig_temporal_isolation",
    state: "Hardware gated",
    detail: "Destroy/recreate boundary on owned A100/H100 MIG instances.",
    executable: true,
  },
];

const runs: RunRecord[] = [
  {
    id: "run_20260803T020040Z",
    label: "Native release canonical",
    timestamp: "Aug 03 · 02:00 UTC",
    records: 10,
    observations: 0,
    path: "native_driver_direct",
    control: "External native path",
    integrity: "Internally consistent",
    trust: "Embedded key",
    publication: "Protected",
    type: "Native local",
    note: "Canonical native-runner evidence. Publication remains refused because external trust and release provenance are incomplete.",
  },
  {
    id: "run_20260803T011804Z",
    label: "Pinned control battery",
    timestamp: "Aug 03 · 01:18 UTC",
    records: 40,
    observations: 4,
    path: "driver_direct + framework_pooled",
    control: "10 / 10 recovered",
    integrity: "Internally consistent",
    trust: "Embedded key",
    publication: "Eligible",
    type: "Real local",
    note: "Superseding pinned-container control battery. Ten expected framework-pooled canaries recovered; driver-direct residue remained clean.",
  },
  {
    id: "run_20260801T023730Z",
    label: "Full local report card",
    timestamp: "Aug 01 · 23:37 UTC",
    records: 30,
    observations: 16,
    path: "mixed local paths",
    control: "10 / 10 recovered",
    integrity: "Internally consistent",
    trust: "Embedded key",
    publication: "Protected",
    type: "Real local",
    note: "Representative local-lab evidence with independent grades U / B / A / U / C and no composite score.",
  },
  {
    id: "run_20260801T004446Z",
    label: "Superseding identity fix",
    timestamp: "Aug 01 · 00:44 UTC",
    records: 40,
    observations: 0,
    path: "driver_direct + framework_pooled",
    control: "10 / 10 recovered",
    integrity: "Internally consistent",
    trust: "Embedded key",
    publication: "Protected",
    type: "Real local",
    note: "Clean probe-identity re-run. Documentation identifies this as the superseding bundle, while the report generator still excludes it.",
  },
  {
    id: "sim_fixture_leaky",
    label: "Leaky negative fixture",
    timestamp: "Jul 30 · fixture",
    records: 20,
    observations: 0,
    path: "simulated",
    control: "Injected recovery",
    integrity: "Internally consistent",
    trust: "Embedded key",
    publication: "Development only",
    type: "Simulated fixture",
    note: "Deliberately leaky mutation fixture. It proves detection behavior and is never publishable provider evidence.",
  },
];

const reportCards = [
  {
    section: "§13.1",
    grade: "U",
    title: "Memory lifecycle hygiene",
    tone: "unknown",
    basis:
      "Unproven. No driver-direct canaries recovered, but same-model die separation is not yet calibrated.",
  },
  {
    section: "§13.2",
    grade: "B",
    title: "Tenant exposure",
    tone: "good",
    basis:
      "No unexpected visibility in testable observations; two results remained operationally ambiguous.",
  },
  {
    section: "§13.3",
    grade: "A",
    title: "Hardware claim consistency",
    tone: "good",
    basis:
      "Observed topology is strongly consistent with the advertised hardware class.",
  },
  {
    section: "§13.4",
    grade: "U",
    title: "Location consistency",
    tone: "unknown",
    basis:
      "Unproven. The local-lab record has no provider region claim to evaluate.",
  },
  {
    section: "§13.5",
    grade: "C",
    title: "Allocation transparency",
    tone: "warn",
    basis:
      "Allocation model inferred as time-sliced full GPU at 0.80 ranked confidence, not provider-confirmed.",
  },
] as const;

const providers = [
  {
    code: "Provider A",
    type: "Hyperscaler",
    classification: "Full probe OK",
    status: "Reviewed",
    date: "2026-08-03",
    note: "Published policy permits bounded assessment of customer-owned assets under the project constraints.",
    ready: true,
  },
  {
    code: "Provider B",
    type: "Specialist",
    classification: "Written permission",
    status: "Awaiting response",
    date: "2026-08-03",
    note: "Terms prohibit penetration tests and benchmarking without prior written consent.",
    ready: false,
  },
  {
    code: "Provider C",
    type: "Marketplace",
    classification: "Full probe OK",
    status: "Reviewed",
    date: "2026-08-03",
    note: "Policy review is complete for the bounded, canary-only battery on owned rentals.",
    ready: true,
  },
  {
    code: "Provider D",
    type: "Specialist",
    classification: "Written permission",
    status: "Awaiting response",
    date: "2026-08-03",
    note: "No provider run is permitted until a written scope reference is recorded.",
    ready: false,
  },
];

const controlTrend = [
  { run: "00:16", control: 10, direct: 0 },
  { run: "00:44", control: 10, direct: 0 },
  { run: "23:37", control: 10, direct: 0 },
  { run: "00:39", control: 10, direct: 0 },
  { run: "00:41", control: 10, direct: 0 },
  { run: "01:18", control: 10, direct: 0 },
];

const viewCopy: Record<View, { eyebrow: string; title: string; subtitle: string }> = {
  overview: {
    eyebrow: "Control room / Local lab",
    title: "Evidence before assurance.",
    subtitle:
      "Monitor the measurement chain, prepare safe local runs, and inspect what the evidence can—and cannot—support.",
  },
  runs: {
    eyebrow: "Operations / Local execution",
    title: "Run the bounded battery.",
    subtitle:
      "Prepare allowlisted project commands with simulation made explicit. Cloud execution stays locked until a provider adapter exists.",
  },
  probes: {
    eyebrow: "Method / Charter §9",
    title: "Thirteen probe families. Zero hidden claims.",
    subtitle:
      "Every instrument exposes its boundary, current host availability, and the gate that prevents overclaiming.",
  },
  evidence: {
    eyebrow: "Evidence store / Signed JSON",
    title: "Trace every conclusion to a measurement path.",
    subtitle:
      "Inspect local bundles, positive controls, integrity state, provenance limits, and publication eligibility.",
  },
  reports: {
    eyebrow: "Assurance / Charter §13",
    title: "Independent grades, never a composite score.",
    subtitle:
      "U means unproven—not failing. D alone is a failed category and potential disclosure trigger.",
  },
  providers: {
    eyebrow: "Policy matrix / Phase 0 gate",
    title: "Permission is part of the instrument.",
    subtitle:
      "Provider identities stay pseudonymous in the operational view. No reviewed policy, no probe.",
  },
  safety: {
    eyebrow: "Safety kernel / Enforced boundaries",
    title: "A clean result is only credible when refusal works.",
    subtitle:
      "Canary-only search, no raw retention, signed bundles, and publication gates remain visible at every stage.",
  },
};

function downloadText(filename: string, text: string, type = "text/plain") {
  const blob = new Blob([text], { type });
  const href = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = href;
  anchor.download = filename;
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
  URL.revokeObjectURL(href);
}

function ToneChip({
  children,
  tone = "neutral",
}: {
  children: React.ReactNode;
  tone?: "signal" | "info" | "warn" | "danger" | "neutral";
}) {
  return <span className={"tone-chip tone-" + tone}>{children}</span>;
}

function Panel({
  children,
  className = "",
}: {
  children: React.ReactNode;
  className?: string;
}) {
  return <section className={"panel " + className}>{children}</section>;
}

function PanelHeading({
  eyebrow,
  title,
  action,
}: {
  eyebrow: string;
  title: string;
  action?: React.ReactNode;
}) {
  return (
    <div className="panel-heading">
      <div>
        <span className="micro-label">{eyebrow}</span>
        <h2>{title}</h2>
      </div>
      {action}
    </div>
  );
}

export function GhostMeterDashboard() {
  const [activeView, setActiveView] = useState<View>("overview");
  const [mobileOpen, setMobileOpen] = useState(false);
  const [paletteOpen, setPaletteOpen] = useState(false);
  const [paletteQuery, setPaletteQuery] = useState("");
  const [runPlanOpen, setRunPlanOpen] = useState(false);
  const [selectedAction, setSelectedAction] = useState<OperatorAction>(
    operatorActions[1],
  );
  const [selectedRun, setSelectedRun] = useState<RunRecord | null>(null);
  const [probeQuery, setProbeQuery] = useState("");
  const [runQuery, setRunQuery] = useState("");
  const [selectedProbes, setSelectedProbes] = useState<Set<string>>(
    new Set(["environment_inventory"]),
  );
  const [toast, setToast] = useState<string | null>(null);
  const [now, setNow] = useState(new Date());

  useEffect(() => {
    const handleKeyDown = (event: KeyboardEvent) => {
      if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === "k") {
        event.preventDefault();
        setPaletteOpen((open) => !open);
      }
      if (
        event.key === "/" &&
        document.activeElement?.tagName !== "INPUT" &&
        document.activeElement?.tagName !== "TEXTAREA"
      ) {
        event.preventDefault();
        setPaletteOpen(true);
      }
      if (event.key === "Escape") {
        setPaletteOpen(false);
        setRunPlanOpen(false);
        setSelectedRun(null);
      }
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, []);

  useEffect(() => {
    const clock = window.setInterval(() => setNow(new Date()), 30000);
    return () => window.clearInterval(clock);
  }, []);

  useEffect(() => {
    if (!toast) return;
    const timeout = window.setTimeout(() => setToast(null), 2800);
    return () => window.clearTimeout(timeout);
  }, [toast]);

  const filteredPalette = useMemo(() => {
    const items = [
      ...navItems.map((item) => ({
        id: item.id,
        label: item.label,
        hint: item.hint,
        kind: "Navigate",
        run: () => setActiveView(item.id),
      })),
      ...operatorActions.map((item) => ({
        id: item.id,
        label: item.name,
        hint: item.summary,
        kind: "Prepare command",
        run: () => {
          setSelectedAction(item);
          setRunPlanOpen(true);
        },
      })),
    ];
    const query = paletteQuery.trim().toLowerCase();
    if (!query) return items;
    return items.filter(
      (item) =>
        item.label.toLowerCase().includes(query) ||
        item.hint.toLowerCase().includes(query),
    );
  }, [paletteQuery]);

  const filteredProbes = useMemo(() => {
    const query = probeQuery.trim().toLowerCase();
    return probes.filter(
      (probe) =>
        !query ||
        probe.name.toLowerCase().includes(query) ||
        probe.code.toLowerCase().includes(query) ||
        probe.state.toLowerCase().includes(query),
    );
  }, [probeQuery]);

  const filteredRuns = useMemo(() => {
    const query = runQuery.trim().toLowerCase();
    return runs.filter(
      (run) =>
        !query ||
        run.id.toLowerCase().includes(query) ||
        run.label.toLowerCase().includes(query) ||
        run.path.toLowerCase().includes(query) ||
        run.type.toLowerCase().includes(query),
    );
  }, [runQuery]);

  const notify = (message: string) => setToast(message);

  const copy = async (value: string, message: string) => {
    try {
      await navigator.clipboard.writeText(value);
      notify(message);
    } catch {
      downloadText("ghost-meter-command.txt", value);
      notify("Clipboard unavailable — downloaded instead");
    }
  };

  const navigate = (view: View) => {
    setActiveView(view);
    setMobileOpen(false);
    window.scrollTo({ top: 0, behavior: "smooth" });
  };

  const openAction = (action: OperatorAction) => {
    setSelectedAction(action);
    setRunPlanOpen(true);
  };

  const toggleProbe = (probe: Probe) => {
    if (!probe.executable) return;
    setSelectedProbes((current) => {
      const next = new Set(current);
      if (next.has(probe.code)) next.delete(probe.code);
      else next.add(probe.code);
      return next;
    });
  };

  const exportExperiment = () => {
    const selected = probes.filter(
      (probe) => probe.executable && selectedProbes.has(probe.code),
    );
    const yaml = [
      "experiment_id: dashboard-local-draft",
      'description: "Local experiment plan generated by Ghost Meter Control Room"',
      "providers:",
      "  - local-lab",
      "ownership:",
      "  confirmation: researcher-owned",
      "limits:",
      "  max_duration_seconds: 3600",
      "  max_allocation_mib: 4096",
      "probes:",
      ...selected.map((probe) => "  - " + probe.code),
      "parameters:",
      "  size_mib: 32",
      "  cycles: 10",
      "  shared_infrastructure: false",
      "reporting:",
      "  automatic_publication: false",
      "",
    ].join("\n");
    downloadText("ghost-meter-experiment.yaml", yaml, "text/yaml");
    notify("Experiment draft downloaded");
  };

  const current = viewCopy[activeView];

  return (
    <div className="dashboard-shell">
      <div className="ambient-grid" aria-hidden="true" />
      {mobileOpen && (
        <button
          className="sidebar-scrim"
          aria-label="Close navigation"
          onClick={() => setMobileOpen(false)}
        />
      )}

      <aside className={"sidebar " + (mobileOpen ? "sidebar-open" : "")}>
        <div className="brand">
          <div className="brand-mark" aria-hidden="true">
            <Shield size={36} strokeWidth={1.5} />
            <Ghost size={17} strokeWidth={2.2} />
          </div>
          <div className="brand-copy">
            <span className="brand-name">
              GPU<span>-SEAL</span>
            </span>
            <span className="brand-sub">Ghost Meter</span>
          </div>
        </div>

        <div className="nav-section-label">Control room</div>
        <nav className="sidebar-nav" aria-label="Primary navigation">
          {navItems.map((item) => {
            const Icon = item.icon;
            const active = activeView === item.id;
            return (
              <button
                key={item.id}
                className={"nav-item " + (active ? "nav-active" : "")}
                onClick={() => navigate(item.id)}
                aria-current={active ? "page" : undefined}
                title={item.hint}
              >
                <Icon size={18} />
                <span>{item.label}</span>
                {item.id === "providers" && (
                  <span className="nav-count">2/4</span>
                )}
                {item.id === "safety" && (
                  <span className="nav-health" aria-label="Healthy" />
                )}
              </button>
            );
          })}
        </nav>

        <div className="sidebar-spacer" />

        <div className="runtime-card">
          <div className="runtime-head">
            <div className="live-dot live-amber" />
            <span>Simulation only</span>
          </div>
          <p>CUDA/CuPy unavailable on this host. Real evidence runs are locked.</p>
          <button onClick={() => openAction(operatorActions[0])}>
            Run preflight <ChevronRight size={14} />
          </button>
        </div>

        <div className="sidebar-meta">
          <span>v0.1.0.dev0</span>
          <span>Phase 0–1</span>
        </div>
      </aside>

      <div className="main-frame">
        <header className="topbar">
          <button
            className="icon-button mobile-menu"
            aria-label="Open navigation"
            onClick={() => setMobileOpen(true)}
          >
            <Menu size={19} />
          </button>

          <button className="environment-control" aria-label="Current environment">
            <span className="live-dot live-amber" />
            <span>
              <small>Environment</small>
              Local lab
            </span>
          </button>

          <button className="command-trigger" onClick={() => setPaletteOpen(true)}>
            <Search size={16} />
            <span>Search views, runs, and operations</span>
            <kbd>⌘ K</kbd>
          </button>

          <div className="topbar-source">
            <Radio size={14} />
            <span>
              Workspace snapshot
              <small>
                {now.toLocaleTimeString([], {
                  hour: "2-digit",
                  minute: "2-digit",
                })}
              </small>
            </span>
          </div>

          <button
            className="primary-button"
            onClick={() => openAction(operatorActions[1])}
          >
            <Play size={15} fill="currentColor" />
            Prepare local run
          </button>
        </header>

        <main className="content">
          <div className="page-heading enter">
            <div>
              <span className="page-eyebrow">{current.eyebrow}</span>
              <h1>{current.title}</h1>
              <p>{current.subtitle}</p>
            </div>
            <div className="heading-status">
              <span className="status-label">Research state</span>
              <div>
                <span className="live-dot live-signal" />
                Local evidence · no cloud study
              </div>
            </div>
          </div>

          {activeView === "overview" && (
            <OverviewView
              onAction={openAction}
              onRun={setSelectedRun}
              onNavigate={navigate}
            />
          )}
          {activeView === "runs" && (
            <RunsView
              query={runQuery}
              setQuery={setRunQuery}
              filteredRuns={filteredRuns}
              onAction={openAction}
              onRun={setSelectedRun}
            />
          )}
          {activeView === "probes" && (
            <ProbesView
              query={probeQuery}
              setQuery={setProbeQuery}
              filteredProbes={filteredProbes}
              selected={selectedProbes}
              toggleProbe={toggleProbe}
              exportExperiment={exportExperiment}
            />
          )}
          {activeView === "evidence" && (
            <EvidenceView
              query={runQuery}
              setQuery={setRunQuery}
              filteredRuns={filteredRuns}
              onRun={setSelectedRun}
              notify={notify}
            />
          )}
          {activeView === "reports" && <ReportsView notify={notify} />}
          {activeView === "providers" && <ProvidersView />}
          {activeView === "safety" && (
            <SafetyView onAction={openAction} notify={notify} />
          )}
        </main>
      </div>

      {paletteOpen && (
        <div
          className="modal-backdrop"
          role="presentation"
          onMouseDown={(event) => {
            if (event.target === event.currentTarget) setPaletteOpen(false);
          }}
        >
          <div className="command-palette" role="dialog" aria-modal="true">
            <div className="palette-input">
              <Command size={18} />
              <input
                autoFocus
                value={paletteQuery}
                onChange={(event) => setPaletteQuery(event.target.value)}
                placeholder="Search the control room…"
                aria-label="Search commands"
              />
              <kbd>Esc</kbd>
            </div>
            <div className="palette-results">
              {filteredPalette.length ? (
                filteredPalette.map((item, index) => (
                  <button
                    key={item.kind + item.id}
                    className={index === 0 ? "palette-highlight" : ""}
                    onClick={() => {
                      item.run();
                      setPaletteOpen(false);
                      setPaletteQuery("");
                    }}
                  >
                    <span>
                      <strong>{item.label}</strong>
                      <small>{item.hint}</small>
                    </span>
                    <span className="palette-kind">{item.kind}</span>
                  </button>
                ))
              ) : (
                <div className="empty-state">No matching view or operation.</div>
              )}
            </div>
            <div className="palette-footer">
              <span>↑↓ navigate</span>
              <span>↵ open</span>
              <span>Esc close</span>
            </div>
          </div>
        </div>
      )}

      {runPlanOpen && (
        <RunPlanModal
          action={selectedAction}
          setAction={setSelectedAction}
          onClose={() => setRunPlanOpen(false)}
          copy={copy}
          notify={notify}
        />
      )}

      {selectedRun && (
        <RunInspector run={selectedRun} onClose={() => setSelectedRun(null)} />
      )}

      {toast && (
        <div className="toast" role="status">
          <CheckCircle2 size={16} />
          {toast}
        </div>
      )}
    </div>
  );
}

function OverviewView({
  onAction,
  onRun,
  onNavigate,
}: {
  onAction: (action: OperatorAction) => void;
  onRun: (run: RunRecord) => void;
  onNavigate: (view: View) => void;
}) {
  return (
    <div className="view-stack">
      <div className="mission-grid enter enter-1">
        <Panel className="mission-panel">
          <div className="mission-topline">
            <ToneChip tone="signal">Phase 0–1 complete</ToneChip>
            <span className="source-stamp">
              <CircleDot size={12} />
              Repository snapshot · 03 Aug 2026
            </span>
          </div>
          <div className="mission-copy">
            <span className="micro-label">Mission state</span>
            <h2>No cloud claim exists yet.</h2>
            <p>
              The local instrument is working, the canary control recovers its
              own marker, and the driver-direct path recovered none. Provider
              conclusions remain gated by policy, ethics, and rental evidence.
            </p>
          </div>
          <div className="gate-rail">
            <div className="gate gate-done">
              <span><Check size={13} /></span>
              <strong>Probe core</strong>
              <small>13 / 13 built</small>
            </div>
            <div className="gate gate-done">
              <span><Check size={13} /></span>
              <strong>Safety kernel</strong>
              <small>38 / 38 controls</small>
            </div>
            <div className="gate gate-current">
              <span>2</span>
              <strong>Provider policy</strong>
              <small>2 / 4 reviewed</small>
            </div>
            <div className="gate gate-locked">
              <span><LockKeyhole size={12} /></span>
              <strong>Provider pilot</strong>
              <small>Runtime absent</small>
            </div>
          </div>
          <div className="mission-footer">
            <span><ShieldCheck size={15} /> Canary-only policy enforced</span>
            <span><CloudOff size={15} /> Cloud adapters: 0</span>
            <button onClick={() => onNavigate("safety")}>
              Inspect release gates <ChevronRight size={14} />
            </button>
          </div>
        </Panel>

        <Panel className="actions-panel">
          <PanelHeading
            eyebrow="Allowlisted operations"
            title="Operator actions"
            action={<SquareTerminal size={17} />}
          />
          <div className="action-list">
            {operatorActions.map((action) => {
              const Icon = action.icon;
              return (
                <button
                  key={action.id}
                  className="operator-action"
                  onClick={() => onAction(action)}
                >
                  <span className={"action-icon action-" + action.tone}>
                    <Icon size={16} />
                  </span>
                  <span>
                    <strong>{action.name}</strong>
                    <small>{action.summary}</small>
                  </span>
                  <ChevronRight size={15} />
                </button>
              );
            })}
          </div>
        </Panel>
      </div>

      <div className="metric-strip enter enter-2">
        <MetricCard
          label="Evidence bundles"
          value="23"
          detail="Local workspace · 20 direct, 3 fixtures"
          icon={FileJson}
        />
        <MetricCard
          label="Probe families"
          value="13"
          detail="Implemented · host currently simulation-only"
          icon={Cpu}
        />
        <MetricCard
          label="Policy reviews"
          value="2 / 4"
          detail="Providers A and C cleared for bounded probing"
          icon={BookOpenCheck}
        />
        <MetricCard
          label="Injected controls"
          value="38 / 38"
          detail="Policy violations rejected by the safety suite"
          icon={ShieldCheck}
        />
      </div>

      <div className="analysis-grid enter enter-3">
        <Panel className="chart-panel">
          <PanelHeading
            eyebrow="Measurement paths · n=6 batteries"
            title="Canary recovery by boundary"
            action={<ToneChip tone="info">Expected control behavior</ToneChip>}
          />
          <div className="chart-copy">
            <p>
              Framework-pooled recovery proves detection capability.
              Driver-direct recovery is the provider-sensitive measurement.
            </p>
            <div className="chart-legend-copy">
              <span><i className="legend-signal" /> Framework pooled</span>
              <span><i className="legend-info" /> Driver direct</span>
            </div>
          </div>
          <div className="chart-wrap" aria-label="Canary recovery trend chart">
            <ResponsiveContainer width="100%" height="100%">
              <LineChart data={controlTrend} margin={{ top: 10, right: 12, left: -22, bottom: 0 }}>
                <CartesianGrid stroke="#17313b" strokeDasharray="2 5" vertical={false} />
                <XAxis
                  dataKey="run"
                  stroke="#718286"
                  tick={{ fontSize: 11, fill: "#718286" }}
                  tickLine={false}
                  axisLine={{ stroke: "#17313b" }}
                />
                <YAxis
                  domain={[0, 10]}
                  ticks={[0, 5, 10]}
                  stroke="#718286"
                  tick={{ fontSize: 11, fill: "#718286" }}
                  tickLine={false}
                  axisLine={false}
                />
                <Tooltip
                  cursor={{ stroke: "#2d4c56" }}
                  contentStyle={{
                    background: "#071219",
                    border: "1px solid #2d4c56",
                    borderRadius: "8px",
                    color: "#f3f7f5",
                    fontSize: "12px",
                  }}
                />
                <Line
                  type="linear"
                  dataKey="control"
                  name="Framework pooled"
                  stroke="#76d842"
                  strokeWidth={2}
                  dot={false}
                  activeDot={{ r: 4, fill: "#95f05c" }}
                />
                <Line
                  type="linear"
                  dataKey="direct"
                  name="Driver direct"
                  stroke="#4ccbc0"
                  strokeWidth={2}
                  dot={false}
                  activeDot={{ r: 4, fill: "#4ccbc0" }}
                />
              </LineChart>
            </ResponsiveContainer>
          </div>
        </Panel>

        <Panel className="readiness-panel">
          <PanelHeading
            eyebrow="Release readiness"
            title="Three gates remain"
            action={<LockKeyhole size={17} />}
          />
          <div className="readiness-score">
            <div className="readiness-ring" aria-label="Seven of ten release checks complete">
              <span>7</span>
              <small>/ 10</small>
            </div>
            <div>
              <strong>Local instrument ready</strong>
              <p>Provider study remains correctly blocked.</p>
            </div>
          </div>
          <div className="readiness-list">
            <div className="readiness-row ready">
              <CheckCircle2 size={15} />
              <span><strong>Probe families</strong><small>13 / 13 implemented</small></span>
            </div>
            <div className="readiness-row ready">
              <CheckCircle2 size={15} />
              <span><strong>Pre-registration</strong><small>Written and dated</small></span>
            </div>
            <div className="readiness-row waiting">
              <TriangleAlert size={15} />
              <span><strong>Ethics sign-off</strong><small>Reviewer approval outstanding</small></span>
            </div>
            <div className="readiness-row waiting">
              <TriangleAlert size={15} />
              <span><strong>Native probe port</strong><small>ADR-001 Phase 2 gate</small></span>
            </div>
            <div className="readiness-row waiting">
              <TriangleAlert size={15} />
              <span><strong>Provider policy</strong><small>2 reviews still awaiting permission</small></span>
            </div>
          </div>
        </Panel>
      </div>

      <Panel className="report-strip enter enter-4">
        <PanelHeading
          eyebrow="Representative local card · no composite score"
          title="Independent assurance categories"
          action={
            <button className="text-button" onClick={() => onNavigate("reports")}>
              Full report card <ChevronRight size={14} />
            </button>
          }
        />
        <div className="grade-grid">
          {reportCards.map((card) => (
            <div className={"grade-card grade-" + card.tone} key={card.title}>
              <span className="micro-label">{card.section}</span>
              <div className="grade-line">
                <span className="grade-value">{card.grade}</span>
                <strong>{card.title}</strong>
              </div>
              <p>{card.basis}</p>
            </div>
          ))}
        </div>
      </Panel>

      <div className="lower-grid enter enter-5">
        <Panel className="recent-panel">
          <PanelHeading
            eyebrow="Evidence store"
            title="Recent bundles"
            action={
              <button className="text-button" onClick={() => onNavigate("evidence")}>
                Explore all <ChevronRight size={14} />
              </button>
            }
          />
          <RunTable rows={runs.slice(0, 4)} onRun={onRun} compact />
        </Panel>
        <Panel className="invariants-panel">
          <PanelHeading
            eyebrow="Safety invariants"
            title="Protected by design"
            action={<Shield size={17} />}
          />
          <div className="invariant-list">
            {[
              ["Canary-only search", "Caller-supplied patterns refused"],
              ["Raw unknown memory", "Never retained or rendered"],
              ["Evidence integrity", "All 23 bundles internally consistent"],
              ["Publication control", "19 of 23 protected from auto-release"],
            ].map(([title, detail]) => (
              <div className="invariant" key={title}>
                <span><Check size={13} /></span>
                <div><strong>{title}</strong><small>{detail}</small></div>
              </div>
            ))}
          </div>
          <div className="safety-footer">
            <KeyRound size={15} />
            Embedded-key verification proves internal consistency, not external trust.
          </div>
        </Panel>
      </div>
    </div>
  );
}

function MetricCard({
  label,
  value,
  detail,
  icon: Icon,
}: {
  label: string;
  value: string;
  detail: string;
  icon: LucideIcon;
}) {
  return (
    <Panel className="metric-card">
      <div className="metric-top">
        <span>{label}</span>
        <Icon size={17} />
      </div>
      <strong>{value}</strong>
      <small>{detail}</small>
    </Panel>
  );
}

function RunsView({
  query,
  setQuery,
  filteredRuns,
  onAction,
  onRun,
}: {
  query: string;
  setQuery: (value: string) => void;
  filteredRuns: RunRecord[];
  onAction: (action: OperatorAction) => void;
  onRun: (run: RunRecord) => void;
}) {
  return (
    <div className="view-stack">
      <div className="operation-grid enter enter-1">
        <Panel className="run-launch-panel">
          <div className="run-launch-copy">
            <span className="micro-label">Current host · preflight result</span>
            <h2>Simulation is available. Evidence mode is not.</h2>
            <p>
              This Windows host has no CuPy/CUDA backend. The control room will
              never relabel a simulation fallback as real measurement evidence.
            </p>
          </div>
          <div className="host-specs">
            <div><span>OS</span><strong>Windows</strong></div>
            <div><span>Python</span><strong>3.14.2</strong></div>
            <div><span>CUDA</span><strong>Unavailable</strong></div>
            <div><span>Run mode</span><strong>Simulation</strong></div>
          </div>
          <div className="run-launch-actions">
            <button className="primary-button" onClick={() => onAction(operatorActions[1])}>
              <Play size={15} fill="currentColor" /> Prepare Phase 1
            </button>
            <button className="secondary-button" onClick={() => onAction(operatorActions[0])}>
              <RefreshCw size={15} /> Re-run preflight
            </button>
          </div>
        </Panel>
        <Panel className="cloud-lock-panel">
          <CloudOff size={26} />
          <div>
            <span className="micro-label">Provider runtime</span>
            <h2>Cloud controls unavailable</h2>
            <p>
              The repository defines a runtime protocol but ships zero provider
              adapters. Launch, execute, and terminate remain disabled.
            </p>
          </div>
          <div className="preflight-mini">
            <span className="mini-pass"><Check size={12} /> Policy model</span>
            <span className="mini-fail"><X size={12} /> Runtime adapter</span>
            <span className="mini-fail"><X size={12} /> Instance inventory</span>
          </div>
        </Panel>
      </div>

      <Panel className="section-panel enter enter-2">
        <PanelHeading
          eyebrow="Allowlisted command catalogue"
          title="Prepare an operation"
          action={<ToneChip tone="info">No arbitrary shell input</ToneChip>}
        />
        <div className="operation-cards">
          {operatorActions.map((action) => {
            const Icon = action.icon;
            return (
              <button
                className="operation-card"
                key={action.id}
                onClick={() => onAction(action)}
              >
                <span className={"action-icon action-" + action.tone}>
                  <Icon size={18} />
                </span>
                <span className="micro-label">
                  {action.tone === "write"
                    ? "Produces local output"
                    : action.tone === "verify"
                      ? "Verification job"
                      : "Read only"}
                </span>
                <strong>{action.name}</strong>
                <p>{action.summary}</p>
                <span className="operation-open">Configure <ChevronRight size={14} /></span>
              </button>
            );
          })}
        </div>
      </Panel>

      <Panel className="section-panel enter enter-3">
        <PanelHeading
          eyebrow="Workspace evidence"
          title="Run history"
          action={
            <div className="search-control">
              <Search size={14} />
              <input
                value={query}
                onChange={(event) => setQuery(event.target.value)}
                placeholder="Filter run ID or path"
                aria-label="Filter runs"
              />
            </div>
          }
        />
        <RunTable rows={filteredRuns} onRun={onRun} />
      </Panel>
    </div>
  );
}

function ProbesView({
  query,
  setQuery,
  filteredProbes,
  selected,
  toggleProbe,
  exportExperiment,
}: {
  query: string;
  setQuery: (value: string) => void;
  filteredProbes: Probe[];
  selected: Set<string>;
  toggleProbe: (probe: Probe) => void;
  exportExperiment: () => void;
}) {
  const executableCount = probes.filter((probe) => probe.executable).length;
  return (
    <div className="view-stack">
      <div className="probe-summary enter enter-1">
        <Panel>
          <span className="micro-label">Implementation</span>
          <strong>13 / 13</strong>
          <p>Chartered families built and covered by tests.</p>
        </Panel>
        <Panel>
          <span className="micro-label">Experiment enum</span>
          <strong>11</strong>
          <p>Runnable values; §9.8b and §9.11 share analysis paths.</p>
        </Panel>
        <Panel>
          <span className="micro-label">Current host</span>
          <strong>1 / 13</strong>
          <p>Environment inventory can run without CUDA.</p>
        </Panel>
        <Panel>
          <span className="micro-label">Hardware gated</span>
          <strong>3</strong>
          <p>Attestation, channel binding, and MIG require datacentre silicon.</p>
        </Panel>
      </div>

      <div className="probe-workspace enter enter-2">
        <Panel className="probe-catalogue">
          <PanelHeading
            eyebrow="Charter §9"
            title="Probe availability matrix"
            action={
              <div className="search-control">
                <Search size={14} />
                <input
                  value={query}
                  onChange={(event) => setQuery(event.target.value)}
                  placeholder="Search probes"
                  aria-label="Search probes"
                />
              </div>
            }
          />
          <div className="probe-list">
            {filteredProbes.map((probe) => {
              const checked = selected.has(probe.code);
              const tone =
                probe.state === "Local capable"
                  ? "signal"
                  : probe.state === "Host blocked"
                    ? "neutral"
                    : "warn";
              return (
                <button
                  key={probe.section}
                  className={
                    "probe-row " +
                    (checked ? "probe-selected " : "") +
                    (!probe.executable ? "probe-derived" : "")
                  }
                  onClick={() => toggleProbe(probe)}
                  aria-pressed={checked}
                >
                  <span className="probe-check">
                    {checked ? (
                      <Check size={13} />
                    ) : probe.executable ? (
                      <span />
                    ) : (
                      <LockKeyhole size={12} />
                    )}
                  </span>
                  <span className="probe-section">{probe.section}</span>
                  <span className="probe-name">
                    <strong>{probe.name}</strong>
                    <small>{probe.code}</small>
                  </span>
                  <span className="probe-detail">{probe.detail}</span>
                  <ToneChip tone={tone}>{probe.state}</ToneChip>
                </button>
              );
            })}
          </div>
        </Panel>

        <Panel className="experiment-builder">
          <PanelHeading
            eyebrow="Experiment draft"
            title="Local battery"
            action={<FileCode2 size={17} />}
          />
          <div className="builder-stat">
            <strong>{selected.size}</strong>
            <span>of {executableCount} runnable families selected</span>
          </div>
          <div className="selected-probe-list">
            {Array.from(selected).length ? (
              Array.from(selected).map((code) => (
                <span key={code}><Check size={12} />{code}</span>
              ))
            ) : (
              <p>Select at least one runnable family.</p>
            )}
          </div>
          <div className="builder-fields">
            <label>
              Buffer
              <span>32 MiB</span>
            </label>
            <label>
              Cycles
              <span>10</span>
            </label>
            <label>
              Duration ceiling
              <span>3,600 s</span>
            </label>
            <label>
              Publication
              <span>Manual only</span>
            </label>
          </div>
          <div className="builder-note">
            <Info size={15} />
            This downloads a schema-aligned draft. The repository has no YAML
            experiment orchestrator, so saving the file does not execute it.
          </div>
          <button
            className="primary-button builder-download"
            disabled={!selected.size}
            onClick={exportExperiment}
          >
            <Download size={15} /> Download experiment YAML
          </button>
        </Panel>
      </div>
    </div>
  );
}

function EvidenceView({
  query,
  setQuery,
  filteredRuns,
  onRun,
  notify,
}: {
  query: string;
  setQuery: (value: string) => void;
  filteredRuns: RunRecord[];
  onRun: (run: RunRecord) => void;
  notify: (message: string) => void;
}) {
  const exportIndex = () => {
    downloadText(
      "ghost-meter-evidence-index.json",
      JSON.stringify({ generated_at: new Date().toISOString(), runs }, null, 2),
      "application/json",
    );
    notify("Evidence index downloaded");
  };
  return (
    <div className="view-stack">
      <Panel className="path-explainer enter enter-1">
        <div className="path-copy">
          <span className="micro-label">Critical interpretation rule</span>
          <h2>Canary recovery is path-dependent.</h2>
          <p>
            Treating every owned-canary match as a finding would invert the
            experiment. The control is supposed to recover its marker.
          </p>
        </div>
        <div className="path-comparison">
          <div className="path-card control-path">
            <span className="micro-label">§9.4 · framework_pooled</span>
            <div><BadgeCheck size={21} /><strong>10 / 10 recovered</strong></div>
            <p>Positive control passed. Detection capability demonstrated.</p>
          </div>
          <div className="path-connector" aria-hidden="true">
            <ChevronRight size={18} />
          </div>
          <div className="path-card direct-path">
            <span className="micro-label">§9.3 · driver_direct</span>
            <div><Fingerprint size={21} /><strong>0 / 30 recovered</strong></div>
            <p>No residue observed locally. Sanitisation remains unproven.</p>
          </div>
        </div>
      </Panel>

      <div className="evidence-metrics enter enter-2">
        <Panel>
          <FileJson size={17} />
          <span>Signed bundles</span>
          <strong>23</strong>
          <small>20 local · 3 simulated fixtures</small>
        </Panel>
        <Panel>
          <KeyRound size={17} />
          <span>Internal integrity</span>
          <strong>23 / 23</strong>
          <small>Embedded-key verification</small>
        </Panel>
        <Panel>
          <ShieldCheck size={17} />
          <span>Publication eligible</span>
          <strong>4</strong>
          <small>Still requires coordinated review</small>
        </Panel>
        <Panel>
          <FileSearch size={17} />
          <span>External trust</span>
          <strong>0</strong>
          <small>No trusted keyring supplied</small>
        </Panel>
      </div>

      <Panel className="section-panel enter enter-3">
        <PanelHeading
          eyebrow="Local evidence index"
          title="Signed bundles"
          action={
            <div className="table-actions">
              <div className="search-control">
                <Search size={14} />
                <input
                  value={query}
                  onChange={(event) => setQuery(event.target.value)}
                  placeholder="Filter evidence"
                  aria-label="Filter evidence"
                />
              </div>
              <button className="secondary-button compact-button" onClick={exportIndex}>
                <Download size={14} /> Export index
              </button>
            </div>
          }
        />
        <RunTable rows={filteredRuns} onRun={onRun} />
      </Panel>

      <Panel className="consistency-note enter enter-4">
        <TriangleAlert size={18} />
        <div>
          <strong>Generator exclusion needs review</strong>
          <p>
            The report generator excludes every filename mentioned in the
            mislabelled-run document—including a clean superseding run the same
            document says to cite. The dashboard preserves both statuses rather
            than silently correcting the repository.
          </p>
        </div>
        <ToneChip tone="warn">Repository inconsistency</ToneChip>
      </Panel>
    </div>
  );
}

function ReportsView({ notify }: { notify: (message: string) => void }) {
  const exportReport = () => {
    downloadText(
      "ghost-meter-local-report-card.json",
      JSON.stringify(
        {
          provider_code: "local-lab",
          note: "Independent category grades. No composite score. U means unproven, not failing.",
          categories: reportCards,
          attestation: {
            available: false,
            evidence_valid: null,
            channel_bound: null,
          },
        },
        null,
        2,
      ),
      "application/json",
    );
    notify("Report card downloaded");
  };
  return (
    <div className="view-stack">
      <div className="report-principle enter enter-1">
        <div className="principle-mark">
          <span>Σ</span>
          <i />
        </div>
        <div>
          <span className="micro-label">Scoring contract</span>
          <h2>No total. No ranking. No provider leaderboard.</h2>
          <p>
            Memory, exposure, hardware, location, allocation, and attestation
            answer different questions. Collapsing them would manufacture
            certainty the evidence does not contain.
          </p>
        </div>
        <button className="secondary-button" onClick={exportReport}>
          <Download size={15} /> Download JSON
        </button>
      </div>

      <div className="report-card-grid enter enter-2">
        {reportCards.map((card) => (
          <Panel className={"full-grade-card grade-" + card.tone} key={card.title}>
            <div className="full-grade-head">
              <span className="micro-label">{card.section}</span>
              <span className="grade-value">{card.grade}</span>
            </div>
            <h2>{card.title}</h2>
            <p>{card.basis}</p>
            <div className="grade-state">
              {card.grade === "U" ? (
                <><Info size={14} /> Unproven — not a failure</>
              ) : card.grade === "A" || card.grade === "B" ? (
                <><CheckCircle2 size={14} /> Evidence supports this grade</>
              ) : (
                <><TriangleAlert size={14} /> Transparency gap remains</>
              )}
            </div>
          </Panel>
        ))}
      </div>

      <Panel className="attestation-panel enter enter-3">
        <PanelHeading
          eyebrow="§13.6 · separate fields, not a grade"
          title="Attestation assurance"
          action={<ToneChip tone="neutral">H100-class hardware required</ToneChip>}
        />
        <div className="attestation-grid">
          {[
            ["Attestation available", "No", "blocked"],
            ["Evidence retrieved", "Not testable", "unknown"],
            ["Certificate chain", "Not testable", "unknown"],
            ["Firmware measurement", "Not testable", "unknown"],
            ["Driver measurement", "Not testable", "unknown"],
            ["Nonce freshness", "Not testable", "unknown"],
            ["Application channel", "Not bound", "blocked"],
            ["Endpoint identity", "Not testable", "unknown"],
            ["Revocation checked", "Not testable", "unknown"],
            ["Policy match", "Not testable", "unknown"],
          ].map(([label, value, state]) => (
            <div className="attestation-field" key={label}>
              <span className={"field-state field-" + state} />
              <span><small>{label}</small><strong>{value}</strong></span>
            </div>
          ))}
        </div>
      </Panel>
    </div>
  );
}

function ProvidersView() {
  return (
    <div className="view-stack">
      <div className="provider-summary enter enter-1">
        <Panel className="provider-readiness">
          <div className="provider-dial">
            <strong>2</strong><span>/ 4</span>
          </div>
          <div>
            <span className="micro-label">Phase 0 policy matrix</span>
            <h2>Two bounded pilots are policy-eligible.</h2>
            <p>
              Eligibility is not evidence and does not provision an instance.
              Ownership, runtime, budget, duration, and publication gates still apply.
            </p>
          </div>
        </Panel>
        <Panel className="provider-lock">
          <LockKeyhole size={22} />
          <div>
            <span className="micro-label">Execution status</span>
            <h2>All provider launches disabled</h2>
            <p>No ProviderRuntime implementation exists in the repository.</p>
          </div>
        </Panel>
      </div>

      <div className="provider-grid enter enter-2">
        {providers.map((provider) => (
          <Panel
            className={"provider-card " + (provider.ready ? "provider-ready" : "provider-waiting")}
            key={provider.code}
          >
            <div className="provider-card-head">
              <div className="provider-monogram">{provider.code.slice(-1)}</div>
              <div>
                <span className="micro-label">{provider.type}</span>
                <h2>{provider.code}</h2>
              </div>
              <ToneChip tone={provider.ready ? "signal" : "warn"}>
                {provider.status}
              </ToneChip>
            </div>
            <div className="provider-classification">
              <span>Classification</span>
              <strong>
                {provider.ready ? <BadgeCheck size={15} /> : <LockKeyhole size={14} />}
                {provider.classification}
              </strong>
            </div>
            <p>{provider.note}</p>
            <div className="provider-meta">
              <span>Reviewed on</span><strong>{provider.date}</strong>
              <span>Fresh until</span><strong>2027-08-03</strong>
              <span>Permission ref.</span><strong>{provider.ready ? "Policy basis" : "Pending"}</strong>
            </div>
            <button className="secondary-button provider-button">
              <FileSearch size={14} /> Review policy record
            </button>
          </Panel>
        ))}
      </div>

      <Panel className="provider-preflight enter enter-3">
        <PanelHeading
          eyebrow="Required before any provider run"
          title="Seven-point execution preflight"
          action={<Settings2 size={17} />}
        />
        <div className="preflight-grid">
          {[
            ["Policy reviewed", "2 / 4", true],
            ["Written permission", "2 exempt · 2 pending", false],
            ["Asset ownership", "Per-run confirmation", false],
            ["Budget reserved", "No ledger attached", false],
            ["Duration ≤ 1 hour", "Hard ceiling", true],
            ["Hardware support", "Rental required", false],
            ["Publication manual", "90 + 30 day process", true],
          ].map(([label, value, pass]) => (
            <div className="preflight-item" key={String(label)}>
              <span className={pass ? "preflight-pass" : "preflight-pending"}>
                {pass ? <Check size={13} /> : <LockKeyhole size={12} />}
              </span>
              <span><strong>{label}</strong><small>{value}</small></span>
            </div>
          ))}
        </div>
      </Panel>
    </div>
  );
}

function SafetyView({
  onAction,
  notify,
}: {
  onAction: (action: OperatorAction) => void;
  notify: (message: string) => void;
}) {
  const copyPolicy = () => {
    const policy = [
      "canary_only_search=true",
      "raw_unknown_memory_retained=false",
      "unknown_memory_rendered=false",
      "automatic_publication=false",
      "max_duration_seconds=3600",
      "max_allocation_mib=4096",
      "public_provider_ranking=false",
    ].join("\n");
    navigator.clipboard.writeText(policy).then(
      () => notify("Safety policy copied"),
      () => {
        downloadText("ghost-meter-safety-policy.txt", policy);
        notify("Safety policy downloaded");
      },
    );
  };
  return (
    <div className="view-stack">
      <Panel className="safety-hero enter enter-1">
        <div className="safety-emblem">
          <Shield size={72} strokeWidth={1.1} />
          <LockKeyhole size={24} />
        </div>
        <div>
          <span className="micro-label">Enforced-safe layer</span>
          <h2>Unknown memory has one read door.</h2>
          <p>
            SafeBuffer reduces raw allocations to allowlisted statistics. The
            system never exposes unknown bytes to the report, operator, or UI.
          </p>
        </div>
        <div className="safety-hero-status">
          <span><CheckCircle2 size={16} /> Static policy checks healthy</span>
          <strong>38 / 38</strong>
          <small>Injected violations caught</small>
        </div>
      </Panel>

      <div className="safety-grid enter enter-2">
        {[
          {
            title: "Canary-only search",
            detail: "No API accepts a caller-supplied memory pattern.",
            section: "ETHICS §7.2",
            icon: Fingerprint,
          },
          {
            title: "No raw retention",
            detail: "Unknown VRAM is reduced to aggregates and discarded.",
            section: "Data policy",
            icon: HardDrive,
          },
          {
            title: "No content rendering",
            detail: "Unknown bytes can never become text, media, or a histogram drill-through.",
            section: "Static gate",
            icon: FileSearch,
          },
          {
            title: "Signed evidence",
            detail: "Bundles carry Ed25519 integrity and SHA-256 measurement hashes.",
            section: "Evidence boundary",
            icon: KeyRound,
          },
          {
            title: "Manual publication",
            detail: "A safe result can still be withheld until provenance and disclosure are complete.",
            section: "Disclosure gate",
            icon: LockKeyhole,
          },
          {
            title: "No provider ranking",
            detail: "Independent categories cannot be collapsed into a public leaderboard.",
            section: "Charter §13",
            icon: BarChart3,
          },
        ].map((item) => {
          const Icon = item.icon;
          return (
            <Panel className="safety-card" key={item.title}>
              <div className="safety-card-icon"><Icon size={19} /></div>
              <span className="micro-label">{item.section}</span>
              <h2>{item.title}</h2>
              <p>{item.detail}</p>
              <span className="safety-enforced"><Check size={12} /> Enforced</span>
            </Panel>
          );
        })}
      </div>

      <div className="safety-bottom enter enter-3">
        <Panel className="release-gates">
          <PanelHeading
            eyebrow="Publication pipeline"
            title="Disclosure sequence"
            action={<ToneChip tone="info">90 + 30 days</ToneChip>}
          />
          <div className="disclosure-rail">
            {[
              ["Observed", true],
              ["Reproduced", true],
              ["Method checked", true],
              ["Ownership confirmed", false],
              ["Provider contacted", false],
              ["Retested", false],
              ["Publication cleared", false],
            ].map(([label, complete], index) => (
              <div className={"disclosure-step " + (complete ? "step-complete" : "")} key={String(label)}>
                <span>{complete ? <Check size={12} /> : index + 1}</span>
                <strong>{label}</strong>
              </div>
            ))}
          </div>
        </Panel>
        <Panel className="safety-actions">
          <PanelHeading
            eyebrow="Verification"
            title="Prove the refusal path"
            action={<Zap size={17} />}
          />
          <button className="operator-action" onClick={() => onAction(operatorActions[3])}>
            <span className="action-icon action-verify"><ShieldCheck size={16} /></span>
            <span><strong>Verify safety suite</strong><small>Run 38 injected mutations</small></span>
            <ChevronRight size={15} />
          </button>
          <button className="operator-action" onClick={() => onAction(operatorActions[5])}>
            <span className="action-icon action-safe"><ListChecks size={16} /></span>
            <span><strong>Check release readiness</strong><small>Inspect provenance and policy gates</small></span>
            <ChevronRight size={15} />
          </button>
          <button className="secondary-button policy-copy" onClick={copyPolicy}>
            <Copy size={14} /> Copy invariant summary
          </button>
        </Panel>
      </div>
    </div>
  );
}

function RunTable({
  rows,
  onRun,
  compact = false,
}: {
  rows: RunRecord[];
  onRun: (run: RunRecord) => void;
  compact?: boolean;
}) {
  return (
    <div className={"run-table " + (compact ? "run-table-compact" : "")}>
      <div className="run-table-head">
        <span>Bundle</span>
        <span>Measurement path</span>
        <span>Integrity</span>
        <span>Publication</span>
        <span />
      </div>
      {rows.length ? (
        rows.map((run) => (
          <button className="run-table-row" key={run.id} onClick={() => onRun(run)}>
            <span className="run-primary">
              <i className={run.type === "Simulated fixture" ? "run-fixture" : "run-real"} />
              <span><strong>{run.label}</strong><small>{run.id} · {run.timestamp}</small></span>
            </span>
            <span className="mono-cell">{run.path}</span>
            <span><ToneChip tone="signal"><Check size={11} /> Verified</ToneChip></span>
            <span>
              <ToneChip
                tone={
                  run.publication === "Eligible"
                    ? "signal"
                    : run.publication === "Development only"
                      ? "warn"
                      : "neutral"
                }
              >
                {run.publication}
              </ToneChip>
            </span>
            <span className="row-open"><ChevronRight size={15} /></span>
          </button>
        ))
      ) : (
        <div className="empty-state">No evidence matches this filter.</div>
      )}
    </div>
  );
}

function RunPlanModal({
  action,
  setAction,
  onClose,
  copy,
  notify,
}: {
  action: OperatorAction;
  setAction: (action: OperatorAction) => void;
  onClose: () => void;
  copy: (value: string, message: string) => Promise<void>;
  notify: (message: string) => void;
}) {
  const [cycles, setCycles] = useState(10);
  const [size, setSize] = useState(32);

  const configuredCommand = useMemo(() => {
    if (action.id !== "phase1" && action.id !== "phase2") return action.command;
    return action.command
      .replace("--size-mib 32", "--size-mib " + Math.max(1, Math.min(size, 4096)))
      .replace("--cycles 10", "--cycles " + Math.max(1, Math.min(cycles, 100)));
  }, [action, cycles, size]);

  const downloadLauncher = () => {
    downloadText(
      "ghost-meter-" + action.id + ".ps1",
      [
        "# Ghost Meter allowlisted local operation",
        "# Generated by the Control Room. Review before execution.",
        "# Current host is simulation-only; --simulate is intentionally explicit.",
        configuredCommand,
        "",
      ].join("\n"),
    );
    notify("Launch script downloaded");
  };

  return (
    <div
      className="modal-backdrop"
      role="presentation"
      onMouseDown={(event) => {
        if (event.target === event.currentTarget) onClose();
      }}
    >
      <div className="run-modal" role="dialog" aria-modal="true" aria-labelledby="run-plan-title">
        <div className="modal-head">
          <div>
            <span className="micro-label">Allowlisted local operation</span>
            <h2 id="run-plan-title">Prepare run plan</h2>
          </div>
          <button className="icon-button" onClick={onClose} aria-label="Close run plan">
            <X size={18} />
          </button>
        </div>

        <div className="modal-body">
          <label className="field-label">
            Operation
            <select
              value={action.id}
              onChange={(event) => {
                const next = operatorActions.find((item) => item.id === event.target.value);
                if (next) setAction(next);
              }}
            >
              {operatorActions.map((item) => (
                <option value={item.id} key={item.id}>{item.name}</option>
              ))}
            </select>
          </label>

          {(action.id === "phase1" || action.id === "phase2") && (
            <div className="field-grid">
              <label className="field-label">
                Buffer size · MiB
                <input
                  type="number"
                  min={1}
                  max={4096}
                  value={size}
                  onChange={(event) => setSize(Number(event.target.value))}
                />
                <small>Hard policy ceiling: 4,096 MiB</small>
              </label>
              <label className="field-label">
                Cycles
                <input
                  type="number"
                  min={1}
                  max={100}
                  value={cycles}
                  onChange={(event) => setCycles(Number(event.target.value))}
                />
                <small>Default battery: 10 cycles</small>
              </label>
            </div>
          )}

          <div className="mode-lock">
            <div>
              <span className="live-dot live-amber" />
              <span><strong>Simulation mode locked on</strong><small>CUDA/CuPy unavailable on this host</small></span>
            </div>
            <LockKeyhole size={16} />
          </div>

          <div className="preflight-checks">
            <span className="micro-label">Preflight</span>
            <div><CheckCircle2 size={14} /> Allowlisted command</div>
            <div><CheckCircle2 size={14} /> Duration below 3,600 s ceiling</div>
            <div><CheckCircle2 size={14} /> Output stays local</div>
            <div className="preflight-warning"><TriangleAlert size={14} /> Non-publishable simulation</div>
          </div>

          <div className="command-preview">
            <div>
              <span className="micro-label">Prepared command</span>
              <button
                className="icon-button"
                onClick={() => copy(configuredCommand, "Command copied")}
                aria-label="Copy prepared command"
              >
                <Copy size={15} />
              </button>
            </div>
            <code>{configuredCommand}</code>
          </div>

          <div className="modal-warning">
            <Info size={15} />
            The hosted control room prepares safe commands but cannot execute
            Python against your local GPU. Run the reviewed command from the
            repository root.
          </div>
        </div>

        <div className="modal-footer">
          <button className="secondary-button" onClick={downloadLauncher}>
            <Download size={15} /> Download launcher
          </button>
          <button
            className="primary-button"
            onClick={() => copy(configuredCommand, "Command copied — ready for your terminal")}
          >
            <Copy size={15} /> Copy launch command
          </button>
        </div>
      </div>
    </div>
  );
}

function RunInspector({
  run,
  onClose,
}: {
  run: RunRecord;
  onClose: () => void;
}) {
  const raw = {
    run_id: run.id,
    source: "local workspace snapshot",
    measurement_path: run.path,
    records: run.records,
    observations: run.observations,
    positive_control: run.control,
    integrity: run.integrity,
    trust_model: run.trust,
    publication: run.publication,
    raw_unknown_memory_retained: false,
    unknown_memory_rendered: false,
    canary_only_search: true,
  };
  return (
    <>
      <button className="drawer-scrim" aria-label="Close inspector" onClick={onClose} />
      <aside className="inspector" aria-label="Evidence inspector">
        <div className="inspector-head">
          <div>
            <span className="micro-label">Evidence inspector</span>
            <h2>{run.label}</h2>
            <code>{run.id}</code>
          </div>
          <button className="icon-button" onClick={onClose} aria-label="Close inspector">
            <X size={18} />
          </button>
        </div>
        <div className="inspector-status">
          <ToneChip tone="signal"><Check size={11} /> {run.integrity}</ToneChip>
          <ToneChip tone={run.publication === "Eligible" ? "signal" : "neutral"}>
            {run.publication}
          </ToneChip>
        </div>
        <div className="inspector-section">
          <span className="micro-label">Interpretation</span>
          <p>{run.note}</p>
        </div>
        <div className="inspector-grid">
          <div><span>Evidence type</span><strong>{run.type}</strong></div>
          <div><span>Timestamp</span><strong>{run.timestamp}</strong></div>
          <div><span>Probe records</span><strong>{run.records}</strong></div>
          <div><span>Observations</span><strong>{run.observations}</strong></div>
          <div><span>Measurement path</span><strong>{run.path}</strong></div>
          <div><span>Control</span><strong>{run.control}</strong></div>
        </div>
        <div className="inspector-section">
          <span className="micro-label">Trust boundary</span>
          <div className="trust-note">
            <KeyRound size={16} />
            <p>
              The embedded signature proves the bundle is internally
              consistent. It does not establish externally trusted provenance.
            </p>
          </div>
        </div>
        <div className="inspector-section">
          <span className="micro-label">Safety assertions</span>
          <div className="assertions">
            <span><Check size={12} /> Canary-only search</span>
            <span><Check size={12} /> No raw retention</span>
            <span><Check size={12} /> No unknown-memory rendering</span>
          </div>
        </div>
        <div className="inspector-section raw-json">
          <div className="raw-json-head">
            <span className="micro-label">Index JSON</span>
            <button
              onClick={() =>
                downloadText(run.id + ".index.json", JSON.stringify(raw, null, 2), "application/json")
              }
            >
              <Download size={13} /> Download
            </button>
          </div>
          <pre>{JSON.stringify(raw, null, 2)}</pre>
        </div>
      </aside>
    </>
  );
}
