"use client";

import {
  Activity,
  ArrowRight,
  BadgeCheck,
  BarChart3,
  BookOpen,
  Check,
  CheckCircle2,
  ChevronDown,
  ChevronRight,
  CircleDot,
  Clipboard,
  CloudOff,
  Code2,
  Copy,
  Cpu,
  Database,
  Download,
  ExternalLink,
  Eye,
  FileCheck2,
  FileJson,
  FileSearch,
  Fingerprint,
  FlaskConical,
  Ghost,
  GitFork,
  Globe2,
  HardDrive,
  Info,
  KeyRound,
  Layers3,
  LockKeyhole,
  Menu,
  MemoryStick,
  Search,
  Shield,
  ShieldCheck,
  SquareTerminal,
  TestTube2,
  TriangleAlert,
  Users,
  X,
} from "lucide-react";
import type { LucideIcon } from "lucide-react";
import {
  CartesianGrid,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { useEffect, useMemo, useState } from "react";

type Page = "home" | "evidence" | "method" | "providers" | "run" | "safety";

type EvidenceRun = {
  id: string;
  title: string;
  timestamp: string;
  type: "Local GPU" | "Native runner" | "Simulation fixture";
  records: number;
  path: string;
  integrity: "Internally consistent" | "Not signature-valid";
  publication: "Automated gate passed" | "Example only" | "Development only";
  control: string;
  result: string;
  note: string;
};

type Probe = {
  section: string;
  title: string;
  code: string;
  group: "Memory" | "Isolation" | "Claims";
  availability: "Local GPU" | "Rental needed" | "Datacentre GPU";
  summary: string;
};

type RunOption = {
  id: string;
  title: string;
  label: string;
  description: string;
  command: string;
  output: string;
  icon: LucideIcon;
};

const GITHUB_URL = "https://github.com/KubixDesiney/gpu-seal";
const DOCS_URL = GITHUB_URL + "/tree/main/docs";

const navItems: Array<{ id: Page; label: string }> = [
  { id: "home", label: "Overview" },
  { id: "evidence", label: "Evidence" },
  { id: "method", label: "Method" },
  { id: "providers", label: "Providers" },
  { id: "run", label: "Run it" },
  { id: "safety", label: "Safety" },
];

const reportCards = [
  {
    grade: "U",
    title: "Memory hygiene",
    section: "§13.1",
    state: "Unproven",
    summary:
      "No driver-direct canaries recovered locally, but same-model die separation is not yet calibrated.",
  },
  {
    grade: "B",
    title: "Tenant exposure",
    section: "§13.2",
    state: "Supported",
    summary:
      "No unexpected visibility in the testable local observations; two results remained ambiguous.",
  },
  {
    grade: "A",
    title: "Hardware claim",
    section: "§13.3",
    state: "Supported",
    summary:
      "The observed topology is strongly consistent with the advertised local hardware class.",
  },
  {
    grade: "U",
    title: "Location claim",
    section: "§13.4",
    state: "Unproven",
    summary:
      "The local lab has no provider region claim, so location consistency cannot be evaluated.",
  },
  {
    grade: "C",
    title: "Allocation model",
    section: "§13.5",
    state: "Transparency gap",
    summary:
      "The allocation model was inferred rather than documented by a provider.",
  },
];

const evidenceRuns: EvidenceRun[] = [
  {
    id: "run_20260803T011804Z",
    title: "Canonical pinned local battery",
    timestamp: "03 Aug 2026 · 01:18 UTC",
    type: "Local GPU",
    records: 40,
    path: "driver_direct + framework_pooled",
    integrity: "Internally consistent",
    publication: "Automated gate passed",
    control: "10 / 10 expected recoveries",
    result: "0 driver-direct recoveries",
    note:
      "A pinned battery on a researcher-owned RTX 3050 under WSL2. The framework path recovered its own canary as expected; the driver-direct path recovered none. This is not provider evidence.",
  },
  {
    id: "run_20260801T014549Z",
    title: "Trimmed report-card example",
    timestamp: "01 Aug 2026 · local example",
    type: "Local GPU",
    records: 2,
    path: "mixed local paths",
    integrity: "Not signature-valid",
    publication: "Example only",
    control: "Structure demonstration",
    result: "Grades U / B / A / U / C",
    note:
      "A deliberately trimmed local-lab payload that teaches the report structure. Its original signature no longer validates by design, so it must never be cited as evidence.",
  },
];

const probes: Probe[] = [
  {
    section: "§9.1",
    title: "Environment inventory",
    code: "environment_inventory",
    group: "Isolation",
    availability: "Local GPU",
    summary: "Records tenant-visible OS, container, GPU, CUDA, and namespace facts.",
  },
  {
    section: "§9.2",
    title: "Local/shared sanitisation",
    code: "local_memory_sanitisation",
    group: "Memory",
    availability: "Local GPU",
    summary: "Expected-negative test of kernel-local and shared-memory boundaries.",
  },
  {
    section: "§9.3",
    title: "Device-global VRAM",
    code: "memory_global_read_before_write",
    group: "Memory",
    availability: "Local GPU",
    summary: "Measures a driver-direct allocation before writing user data into it.",
  },
  {
    section: "§9.4",
    title: "Framework allocator control",
    code: "framework_allocator_reuse",
    group: "Memory",
    availability: "Local GPU",
    summary: "Positive control proving the instrument can recover a canary it planted.",
  },
  {
    section: "§9.5",
    title: "Sequential self-canary",
    code: "self_sequential_canary",
    group: "Memory",
    availability: "Rental needed",
    summary: "Checks an owned canary across two separate rentals after identity gating.",
  },
  {
    section: "§9.6",
    title: "Device exposure",
    code: "device_exposure_inventory",
    group: "Isolation",
    availability: "Local GPU",
    summary: "Passively classifies tenant-visible device and namespace exposure.",
  },
  {
    section: "§9.7",
    title: "Allocation model",
    code: "allocation_model_classifier",
    group: "Isolation",
    availability: "Rental needed",
    summary: "Ranks tenancy hypotheses from tenant-visible signals without calling them probabilities.",
  },
  {
    section: "§9.8",
    title: "Topology fingerprint",
    code: "topology_fingerprint",
    group: "Claims",
    availability: "Local GPU",
    summary: "Tests hardware-class consistency using a reproduced topology instrument.",
  },
  {
    section: "§9.8b",
    title: "Same-model separability",
    code: "separability_analysis",
    group: "Claims",
    availability: "Rental needed",
    summary: "Offline evaluator requiring many instances of one advertised model.",
  },
  {
    section: "§9.9",
    title: "Location consistency",
    code: "coarse_location_consistency",
    group: "Claims",
    availability: "Rental needed",
    summary: "Tests coarse jurisdiction consistency against a provider region claim.",
  },
  {
    section: "§9.10",
    title: "Attestation assurance",
    code: "attestation_assurance",
    group: "Claims",
    availability: "Datacentre GPU",
    summary: "Reports ten separate attestation properties rather than one grade.",
  },
  {
    section: "§9.11",
    title: "Application channel binding",
    code: "assess_channel_binding",
    group: "Claims",
    availability: "Datacentre GPU",
    summary: "Checks whether attested evidence is bound to the application channel.",
  },
  {
    section: "§9.12",
    title: "MIG temporal isolation",
    code: "mig_temporal_isolation",
    group: "Isolation",
    availability: "Datacentre GPU",
    summary: "Measures destroy-and-recreate boundaries on owned A100/H100 MIG instances.",
  },
];

const providers = [
  {
    code: "Provider A",
    category: "Hyperscaler",
    status: "Reviewed",
    classification: "Bounded probing permitted",
    note: "Published policy supports the canary-only battery on customer-owned assets.",
    ready: true,
  },
  {
    code: "Provider B",
    category: "GPU specialist",
    status: "Permission pending",
    classification: "Written approval required",
    note: "No probe may run until a written scope reference is recorded.",
    ready: false,
  },
  {
    code: "Provider C",
    category: "Marketplace",
    status: "Reviewed",
    classification: "Bounded probing permitted",
    note: "Policy review is complete for owned rentals under the project limits.",
    ready: true,
  },
  {
    code: "Provider D",
    category: "GPU specialist",
    status: "Permission pending",
    classification: "Written approval required",
    note: "Provider terms require explicit permission before this research begins.",
    ready: false,
  },
];

const runOptions: RunOption[] = [
  {
    id: "setup",
    title: "Install and validate",
    label: "Recommended first",
    description: "Clone the source, install the development extras, run the tests, and inspect this machine's capabilities.",
    command: 'git clone https://github.com/KubixDesiney/gpu-seal.git\ncd gpu-seal\npython -m pip install -e ".[dev]"\npytest tests -q\npython lab/local-runner/smoke.py',
    output: "Tests + capability report",
    icon: Search,
  },
  {
    id: "phase1",
    title: "Run the core controls",
    label: "Local NVIDIA GPU",
    description: "Run the driver-direct memory probe beside its framework positive control.",
    command: "python lab/local-runner/run_phase1.py --out ./out --size-mib 32 --cycles 10",
    output: "Signed local evidence bundle",
    icon: TestTube2,
  },
  {
    id: "phase2",
    title: "Build a local report card",
    label: "Full local battery",
    description: "Run every locally available family and generate independent assurance categories.",
    command: "python lab/local-runner/run_phase2_local.py --out ./out --size-mib 32 --cycles 10",
    output: "Evidence bundle + report card",
    icon: BarChart3,
  },
  {
    id: "safety",
    title: "Verify the safety kernel",
    label: "Contributors",
    description: "Prove that injected policy violations are caught rather than assumed away.",
    command: "bash lab/verify-safety-suite.sh",
    output: "38 negative controls",
    icon: ShieldCheck,
  },
];

const recoveryTrend = [
  { run: "1", control: 1, direct: 0 },
  { run: "2", control: 2, direct: 0 },
  { run: "3", control: 3, direct: 0 },
  { run: "4", control: 4, direct: 0 },
  { run: "5", control: 5, direct: 0 },
  { run: "6", control: 6, direct: 0 },
  { run: "7", control: 7, direct: 0 },
  { run: "8", control: 8, direct: 0 },
  { run: "9", control: 9, direct: 0 },
  { run: "10", control: 10, direct: 0 },
];

function downloadText(filename: string, contents: string, type = "text/plain") {
  const blob = new Blob([contents], { type });
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = filename;
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
  URL.revokeObjectURL(url);
}

function BrandMark({ compact = false }: { compact?: boolean }) {
  return (
    <span className={"brand-mark " + (compact ? "brand-mark-compact" : "")} aria-hidden="true">
      <Shield size={compact ? 34 : 44} strokeWidth={1.45} />
      <Ghost size={compact ? 16 : 21} strokeWidth={2.15} />
    </span>
  );
}

function StatusChip({
  children,
  tone = "neutral",
}: {
  children: React.ReactNode;
  tone?: "signal" | "teal" | "amber" | "neutral";
}) {
  return <span className={"status-chip chip-" + tone}>{children}</span>;
}

function SectionHeader({
  eyebrow,
  title,
  copy,
  action,
}: {
  eyebrow: string;
  title: string;
  copy?: string;
  action?: React.ReactNode;
}) {
  return (
    <div className="section-header">
      <div>
        <span className="eyebrow">{eyebrow}</span>
        <h2>{title}</h2>
        {copy && <p>{copy}</p>}
      </div>
      {action}
    </div>
  );
}

export function GhostMeterDashboard() {
  const [page, setPage] = useState<Page>("home");
  const [mobileOpen, setMobileOpen] = useState(false);
  const [selectedRun, setSelectedRun] = useState<EvidenceRun | null>(null);
  const [toast, setToast] = useState<string | null>(null);

  useEffect(() => {
    const keyHandler = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        setMobileOpen(false);
        setSelectedRun(null);
      }
    };
    window.addEventListener("keydown", keyHandler);
    return () => window.removeEventListener("keydown", keyHandler);
  }, []);

  useEffect(() => {
    const syncPageFromUrl = () => {
      const requested = window.location.hash.slice(1);
      const matched = navItems.find((item) => item.id === requested);
      setPage(matched?.id ?? "home");
      setMobileOpen(false);
    };

    syncPageFromUrl();
    window.addEventListener("hashchange", syncPageFromUrl);
    window.addEventListener("popstate", syncPageFromUrl);
    return () => {
      window.removeEventListener("hashchange", syncPageFromUrl);
      window.removeEventListener("popstate", syncPageFromUrl);
    };
  }, []);

  useEffect(() => {
    if (!toast) return;
    const timeout = window.setTimeout(() => setToast(null), 2600);
    return () => window.clearTimeout(timeout);
  }, [toast]);

  const navigate = (next: Page) => {
    setPage(next);
    setMobileOpen(false);
    const nextUrl = next === "home"
      ? window.location.pathname + window.location.search
      : `#${next}`;
    window.history.pushState({ page: next }, "", nextUrl);
    window.scrollTo({ top: 0, behavior: "smooth" });
  };

  const copyText = async (value: string, message: string) => {
    try {
      await navigator.clipboard.writeText(value);
      setToast(message);
    } catch {
      downloadText("gpu-seal-command.txt", value);
      setToast("Clipboard unavailable — downloaded instead");
    }
  };

  return (
    <div className="public-shell">
      <div className="ambient-field" aria-hidden="true" />
      <header className="site-header">
        <div className="header-inner">
          <button className="site-brand" onClick={() => navigate("home")} aria-label="GPU-SEAL home">
            <BrandMark compact />
            <span className="brand-type">
              <strong>GPU<span>-SEAL</span></strong>
              <small>Ghost Meter</small>
            </span>
          </button>

          <nav className="desktop-nav" aria-label="Main navigation">
            {navItems.map((item) => (
              <button
                key={item.id}
                className={page === item.id ? "nav-current" : ""}
                onClick={() => navigate(item.id)}
                aria-current={page === item.id ? "page" : undefined}
              >
                {item.label}
              </button>
            ))}
          </nav>

          <div className="header-actions">
            <a className="github-link" href={GITHUB_URL} target="_blank" rel="noreferrer">
              <GitFork size={17} />
              <span>GitHub</span>
            </a>
            <button className="header-cta" onClick={() => navigate("run")}>
              Run locally <ArrowRight size={15} />
            </button>
            <button
              className="mobile-toggle"
              onClick={() => setMobileOpen((open) => !open)}
              aria-expanded={mobileOpen}
              aria-label="Toggle navigation"
            >
              {mobileOpen ? <X size={20} /> : <Menu size={20} />}
            </button>
          </div>
        </div>

        {mobileOpen && (
          <nav className="mobile-nav" aria-label="Mobile navigation">
            {navItems.map((item) => (
              <button
                key={item.id}
                className={page === item.id ? "nav-current" : ""}
                onClick={() => navigate(item.id)}
              >
                {item.label}
                <ChevronRight size={15} />
              </button>
            ))}
            <a href={GITHUB_URL} target="_blank" rel="noreferrer">
              GitHub repository <ExternalLink size={14} />
            </a>
          </nav>
        )}
      </header>

      <div className="truth-banner">
        <div className="banner-inner">
          <span className="signal-dot" />
          <strong>Project truth:</strong>
          <span>No cloud-provider measurement study has been run yet.</span>
          <button onClick={() => navigate("evidence")}>
            See what is verified <ArrowRight size={13} />
          </button>
        </div>
      </div>

      <main>
        {page === "home" && (
          <HomePage navigate={navigate} onRun={setSelectedRun} />
        )}
        {page === "evidence" && <EvidencePage onRun={setSelectedRun} />}
        {page === "method" && <MethodPage />}
        {page === "providers" && <ProvidersPage navigate={navigate} />}
        {page === "run" && <RunPage copyText={copyText} />}
        {page === "safety" && <SafetyPage navigate={navigate} />}
      </main>

      <SiteFooter navigate={navigate} />

      {selectedRun && (
        <EvidenceDrawer run={selectedRun} onClose={() => setSelectedRun(null)} />
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

function HomePage({
  navigate,
  onRun,
}: {
  navigate: (page: Page) => void;
  onRun: (run: EvidenceRun) => void;
}) {
  return (
    <>
      <section className="hero section-frame">
        <div className="hero-copy enter">
          <div className="hero-kicker">
            <StatusChip tone="signal"><CircleDot size={11} /> Open source</StatusChip>
            <StatusChip>Pre-alpha · local validation</StatusChip>
          </div>
          <h1>
            Measure the GPU
            <span>you actually rented.</span>
          </h1>
          <p className="hero-lede">
            GPU-SEAL is a tenant-side, canary-only audit framework for GPU
            memory residue, isolation, and hardware claims. It works with
            ordinary tenant privileges and turns assurance into evidence you can inspect.
          </p>
          <div className="hero-actions">
            <button className="primary-cta" onClick={() => navigate("run")}>
              Run on your GPU <ArrowRight size={16} />
            </button>
            <button className="secondary-cta" onClick={() => navigate("evidence")}>
              <Database size={16} /> Inspect an example
            </button>
          </div>
          <div className="hero-trust">
            <span><ShieldCheck size={15} /> Canary-only by design</span>
            <span><KeyRound size={15} /> Signed JSON bundles</span>
            <span><GitFork size={15} /> Apache-2.0</span>
          </div>
        </div>

        <div className="hero-instrument enter enter-late" aria-label="GPU-SEAL measurement overview">
          <div className="instrument-top">
            <span><Activity size={14} /> Evidence path</span>
            <StatusChip tone="teal">Local lab</StatusChip>
          </div>
          <div className="gpu-field" aria-hidden="true">
            <div className="gpu-chip">
              <Cpu size={32} strokeWidth={1.35} />
              <span>VRAM</span>
            </div>
            <div className="memory-banks">
              {Array.from({ length: 18 }).map((_, index) => (
                <i key={index} className={index === 4 || index === 11 ? "bank-active" : ""} />
              ))}
            </div>
            <div className="probe-beam" />
          </div>
          <div className="path-readout">
            <div>
              <span className="path-icon path-control"><BadgeCheck size={16} /></span>
              <span><small>Framework control</small><strong>10 / 10 recovered</strong></span>
              <StatusChip tone="signal">Expected</StatusChip>
            </div>
            <div>
              <span className="path-icon path-direct"><Fingerprint size={16} /></span>
              <span><small>Driver-direct measurement</small><strong>0 / 10 recovered</strong></span>
              <StatusChip tone="teal">Local only</StatusChip>
            </div>
          </div>
          <div className="instrument-note">
            <Info size={14} />
            No residue observed locally is not proof of provider sanitisation.
          </div>
        </div>
      </section>

      <section className="metric-band">
        <div className="section-frame metrics-grid">
          <PublicMetric value="13 / 13" label="Probe families built" note="Charter §9" />
          <PublicMetric value="Complete" label="Native probe core" note="Memory-touching CUDA path" />
          <PublicMetric value="38 / 38" label="Safety controls" note="Injected violations caught" />
          <PublicMetric value="2 / 4" label="Policy reviews" note="Provider pilot gate" />
          <PublicMetric value="0" label="Cloud studies" note="No provider claims yet" accent />
        </div>
      </section>

      <section className="content-section section-frame">
        <SectionHeader
          eyebrow="What it measures"
          title="Three questions your invoice cannot answer."
          copy="GPU-SEAL works from the same unprivileged tenant position as an ordinary customer."
        />
        <div className="pillar-grid">
          <PillarCard
            number="01"
            icon={MemoryStick}
            title="Was memory cleared?"
            copy="Probe VRAM before writing your own payload, using self-minted cryptographic canaries rather than unknown content."
            tags={["Global VRAM", "Allocator reuse", "MIG lifecycle"]}
          />
          <PillarCard
            number="02"
            icon={Layers3}
            title="What isolation did you get?"
            copy="Inventory device exposure and infer whether the allocation behaves like a dedicated, partitioned, or time-sliced GPU."
            tags={["Namespaces", "Allocation model", "Tenant exposure"]}
          />
          <PillarCard
            number="03"
            icon={Fingerprint}
            title="Does the claim match?"
            copy="Compare tenant-visible topology, coarse location, and attestation evidence with the product that was advertised."
            tags={["Topology", "Region", "Attestation"]}
          />
        </div>
      </section>

      <section className="content-section contrast-section">
        <div className="section-frame">
          <SectionHeader
            eyebrow="How to read the evidence"
            title="The control and the measurement must stay separate."
            copy="A recovered canary can mean the test worked—or a lifecycle boundary leaked. The measurement path decides which."
            action={
              <button className="text-action" onClick={() => navigate("method")}>
                Read the method <ArrowRight size={14} />
              </button>
            }
          />
          <div className="interpretation-grid">
            <div className="interpretation-card control-card">
              <div className="interpretation-head">
                <span className="method-ref">§9.4 · framework_pooled</span>
                <StatusChip tone="signal">Positive control</StatusChip>
              </div>
              <div className="interpretation-value">
                <strong>10 / 10</strong>
                <span>owned canaries recovered</span>
              </div>
              <p>
                This is a pass. The framework allocator reused memory that
                GPU-SEAL itself had written, proving the detector can find a marker.
              </p>
            </div>
            <div className="boundary-arrow">
              <span>Separate boundary</span>
              <ArrowRight size={20} />
            </div>
            <div className="interpretation-card direct-card">
              <div className="interpretation-head">
                <span className="method-ref">§9.3 · driver_direct</span>
                <StatusChip tone="teal">Measurement</StatusChip>
              </div>
              <div className="interpretation-value">
                <strong>0 / 30</strong>
                <span>owned canaries recovered</span>
              </div>
              <p>
                Nothing was observed on this local RTX 3050. Without same-model
                die separation, the honest grade remains U: unproven.
              </p>
            </div>
          </div>
        </div>
      </section>

      <section className="content-section section-frame">
        <SectionHeader
          eyebrow="Latest local report card"
          title="Five categories. No deceptive total score."
          copy="Researcher-owned RTX 3050 local example—not a provider result. Each grade answers a different assurance question; U means unproven, not failed."
          action={
            <button className="text-action" onClick={() => onRun(evidenceRuns[1])}>
              Inspect the example <ArrowRight size={14} />
            </button>
          }
        />
        <div className="public-grade-grid">
          {reportCards.map((card) => (
            <article className={"public-grade grade-" + card.grade.toLowerCase()} key={card.title}>
              <span className="method-ref">{card.section}</span>
              <div className="grade-title">
                <strong>{card.grade}</strong>
                <span>{card.title}</span>
              </div>
              <StatusChip tone={card.grade === "A" || card.grade === "B" ? "signal" : card.grade === "C" ? "amber" : "neutral"}>
                {card.state}
              </StatusChip>
              <p>{card.summary}</p>
            </article>
          ))}
        </div>
      </section>

      <section className="content-section section-frame">
        <div className="public-status-card">
          <div className="status-card-copy">
            <span className="eyebrow">Project status · 03 Aug 2026</span>
            <h2>The instrument is local-ready. The provider study is not.</h2>
            <p>
              The probe core, schemas, report cards, and safety gates are built.
              Provider conclusions remain blocked until policy, ethics,
              provider runtime, and rental evidence are in place.
            </p>
            <button className="secondary-cta" onClick={() => navigate("providers")}>
              View provider readiness <ArrowRight size={15} />
            </button>
          </div>
          <div className="public-gates">
            {[
              ["Probe core", "13 / 13", true],
              ["Safety suite", "38 / 38", true],
              ["Provider policy", "2 / 4", false],
              ["Ethics sign-off", "Outstanding", false],
              ["Cloud runtime", "Not implemented", false],
            ].map(([label, value, complete]) => (
              <div className="public-gate" key={String(label)}>
                <span className={complete ? "gate-complete" : "gate-waiting"}>
                  {complete ? <Check size={13} /> : <LockKeyhole size={12} />}
                </span>
                <span><strong>{label}</strong><small>{value}</small></span>
              </div>
            ))}
          </div>
        </div>
      </section>

      <PublicCta navigate={navigate} />
    </>
  );
}

function PublicMetric({
  value,
  label,
  note,
  accent = false,
}: {
  value: string;
  label: string;
  note: string;
  accent?: boolean;
}) {
  return (
    <div className={"public-metric " + (accent ? "metric-accent" : "")}>
      <strong>{value}</strong>
      <span>{label}</span>
      <small>{note}</small>
    </div>
  );
}

function PillarCard({
  number,
  icon: Icon,
  title,
  copy,
  tags,
}: {
  number: string;
  icon: LucideIcon;
  title: string;
  copy: string;
  tags: string[];
}) {
  return (
    <article className="pillar-card">
      <div className="pillar-top">
        <span className="pillar-icon"><Icon size={24} /></span>
        <span className="pillar-number">{number}</span>
      </div>
      <h3>{title}</h3>
      <p>{copy}</p>
      <div className="tag-row">
        {tags.map((tag) => <span key={tag}>{tag}</span>)}
      </div>
    </article>
  );
}

function EvidencePage({ onRun }: { onRun: (run: EvidenceRun) => void }) {
  const [query, setQuery] = useState("");
  const [type, setType] = useState("All");
  const [uploadError, setUploadError] = useState<string | null>(null);
  const [upload, setUpload] = useState<{
    name: string;
    size: string;
    runId: string;
    schema: string;
    probeCount: number;
    reportCard: boolean;
    safetyBlock: boolean;
  } | null>(null);

  const filtered = useMemo(() => {
    const normalized = query.trim().toLowerCase();
    return evidenceRuns.filter((run) => {
      const matchesType = type === "All" || run.type === type;
      const matchesQuery =
        !normalized ||
        run.title.toLowerCase().includes(normalized) ||
        run.id.toLowerCase().includes(normalized) ||
        run.path.toLowerCase().includes(normalized);
      return matchesType && matchesQuery;
    });
  }, [query, type]);

  const inspectBundle = async (event: React.ChangeEvent<HTMLInputElement>) => {
    const input = event.currentTarget;
    const file = input.files?.[0];
    input.value = "";
    if (!file) return;

    setUpload(null);
    setUploadError(null);
    if (file.size > 5 * 1024 * 1024) {
      setUploadError("Choose a JSON bundle smaller than 5 MB.");
      return;
    }

    try {
      const parsed: unknown = JSON.parse(await file.text());
      if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) {
        throw new Error("The top-level JSON value must be an object.");
      }

      const bundle = parsed as Record<string, unknown>;
      setUpload({
        name: file.name,
        size: file.size < 1024 ? `${file.size} B` : `${(file.size / 1024).toFixed(1)} KB`,
        runId: typeof bundle.run_id === "string" ? bundle.run_id : "Not declared",
        schema: typeof bundle.schema_version === "string" ? bundle.schema_version : "Not declared",
        probeCount: Array.isArray(bundle.probes) ? bundle.probes.length : 0,
        reportCard: Boolean(bundle.report_card && typeof bundle.report_card === "object"),
        safetyBlock: Boolean(bundle.safety && typeof bundle.safety === "object"),
      });
    } catch (error) {
      setUploadError(error instanceof Error ? error.message : "This file is not valid JSON.");
    }
  };

  return (
    <div className="page-frame section-frame">
      <PublicPageHero
        eyebrow="Evidence explorer"
        title="Inspect the record, not a marketing claim."
        copy="Open a GPU-SEAL JSON bundle in your browser or study a labelled local example. Your file stays on this device; nothing is uploaded."
        icon={Database}
      />

      <section className="bundle-tool">
        <div className="bundle-tool-copy">
          <span className="eyebrow">Private, client-side inspection</span>
          <h2>Bring your own result bundle.</h2>
          <p>
            The inspector reads only the result envelope: schema, run ID,
            probe count, report-card presence, and safety metadata. It never
            renders unknown-memory content and does not send the file anywhere.
          </p>
        </div>
        <label className="primary-cta upload-button">
          <FileSearch size={16} /> Choose JSON bundle
          <input type="file" accept="application/json,.json" onChange={inspectBundle} />
        </label>
        {upload && (
          <div className="upload-result" role="status">
            <div className="upload-result-head">
              <span><CheckCircle2 size={16} /> Envelope opened locally</span>
              <small>{upload.name} · {upload.size}</small>
            </div>
            <div>
              <span><small>Run ID</small><strong>{upload.runId}</strong></span>
              <span><small>Schema</small><strong>{upload.schema}</strong></span>
              <span><small>Probe records</small><strong>{upload.probeCount}</strong></span>
              <span><small>Expected blocks</small><strong>{upload.reportCard && upload.safetyBlock ? "Present" : "Incomplete"}</strong></span>
            </div>
            <p>Envelope inspection is not schema validation, signature verification, or external provenance.</p>
          </div>
        )}
        {uploadError && (
          <div className="upload-error" role="alert">
            <TriangleAlert size={15} /> {uploadError}
          </div>
        )}
      </section>

      <div className="evidence-overview">
        <div>
          <span>Documented records</span>
          <strong>2</strong>
          <small>One result · one teaching example</small>
        </div>
        <div>
          <span>Teaching sample</span>
          <strong>Trimmed</strong>
          <small>Signature invalid by design</small>
        </div>
        <div>
          <span>Bundle inspection</span>
          <strong>Local</strong>
          <small>File never leaves your browser</small>
        </div>
        <div>
          <span>Cloud-provider runs</span>
          <strong>0</strong>
          <small>No provider claims</small>
        </div>
      </div>

      <div className="chart-and-note">
        <section className="public-panel chart-public">
          <div className="panel-title">
            <div>
              <span className="eyebrow">Canonical pinned battery</span>
              <h2>Cumulative recovery by cycle</h2>
            </div>
            <div className="chart-key">
              <span><i className="key-control" /> Framework control</span>
              <span><i className="key-direct" /> Driver direct</span>
            </div>
          </div>
          <div className="public-chart">
            <ResponsiveContainer width="100%" height="100%">
              <LineChart data={recoveryTrend} margin={{ top: 8, right: 12, left: -22, bottom: 0 }}>
                <CartesianGrid stroke="#17313b" strokeDasharray="2 5" vertical={false} />
                <XAxis
                  dataKey="run"
                  tick={{ fontSize: 10, fill: "#718286" }}
                  tickLine={false}
                  axisLine={{ stroke: "#17313b" }}
                />
                <YAxis
                  domain={[0, 10]}
                  ticks={[0, 5, 10]}
                  tick={{ fontSize: 10, fill: "#718286" }}
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
                    fontSize: "11px",
                  }}
                />
                <Line type="linear" dataKey="control" stroke="#76d842" strokeWidth={2.2} dot={false} />
                <Line type="linear" dataKey="direct" stroke="#4ccbc0" strokeWidth={2.2} dot={false} />
              </LineChart>
            </ResponsiveContainer>
          </div>
        </section>
        <aside className="public-panel evidence-reading">
          <Eye size={24} />
          <span className="eyebrow">Read with care</span>
          <h2>Verified is not the same as trusted.</h2>
          <p>
            An embedded signature proves a bundle is internally consistent. It
            does not establish who controlled the signing key or whether a
            provider claim is externally validated.
          </p>
          <a href={GITHUB_URL + "/blob/main/docs/methodology.md"} target="_blank" rel="noreferrer">
            Methodology <ExternalLink size={13} />
          </a>
        </aside>
      </div>

      <section className="evidence-library">
        <div className="library-head">
          <div>
            <span className="eyebrow">Documented local examples</span>
            <h2>Evidence teaching library</h2>
          </div>
          <div className="library-actions">
            <label className="search-box">
              <Search size={15} />
              <input
                value={query}
                onChange={(event) => setQuery(event.target.value)}
                placeholder="Search run ID or path"
                aria-label="Search evidence"
              />
            </label>
            <a className="download-button" href={GITHUB_URL + "/blob/main/examples/sample-safe-result.json"} target="_blank" rel="noreferrer">
              <FileJson size={14} /> Open sample JSON
            </a>
          </div>
        </div>
        <div className="filter-row" role="group" aria-label="Evidence type">
          {["All", "Local GPU"].map((option) => (
            <button
              key={option}
              className={type === option ? "filter-current" : ""}
              onClick={() => setType(option)}
            >
              {option}
            </button>
          ))}
        </div>
        <div className="evidence-list">
          <div className="evidence-list-head">
            <span>Bundle</span><span>Type</span><span>Measurement path</span><span>Publication</span><span />
          </div>
          {filtered.map((run) => (
            <button className="evidence-row" key={run.id} onClick={() => onRun(run)}>
              <span className="evidence-identity">
                <i className={run.type === "Simulation fixture" ? "fixture-dot" : "evidence-dot"} />
                <span><strong>{run.title}</strong><small>{run.id} · {run.timestamp}</small></span>
              </span>
              <span><StatusChip tone={run.type === "Simulation fixture" ? "amber" : "teal"}>{run.type}</StatusChip></span>
              <code>{run.path}</code>
              <span><StatusChip tone={run.publication === "Automated gate passed" ? "signal" : "neutral"}>{run.publication}</StatusChip></span>
              <ChevronRight size={16} />
            </button>
          ))}
          {!filtered.length && <div className="empty-result">No evidence matches this filter.</div>}
        </div>
      </section>
    </div>
  );
}

function MethodPage() {
  const [query, setQuery] = useState("");
  const [group, setGroup] = useState("All");
  const [expanded, setExpanded] = useState<string | null>("§9.3");

  const filtered = useMemo(() => {
    const normalized = query.trim().toLowerCase();
    return probes.filter((probe) => {
      const matchesGroup = group === "All" || probe.group === group;
      const matchesQuery =
        !normalized ||
        probe.title.toLowerCase().includes(normalized) ||
        probe.code.toLowerCase().includes(normalized) ||
        probe.summary.toLowerCase().includes(normalized);
      return matchesGroup && matchesQuery;
    });
  }, [query, group]);

  return (
    <div className="page-frame section-frame">
      <PublicPageHero
        eyebrow="Method · Charter §9"
        title="Thirteen probes with explicit limits."
        copy="Each family states what it observes, what hardware it needs, and what conclusion it refuses to make."
        icon={FlaskConical}
      />

      <div className="method-intro-grid">
        <article>
          <MemoryStick size={22} />
          <span className="eyebrow">Memory</span>
          <h2>Observe lifecycle boundaries</h2>
          <p>Search only for canaries GPU-SEAL minted itself.</p>
        </article>
        <article>
          <Layers3 size={22} />
          <span className="eyebrow">Isolation</span>
          <h2>Measure the tenant view</h2>
          <p>Inventory exposure without escaping the guest boundary.</p>
        </article>
        <article>
          <Fingerprint size={22} />
          <span className="eyebrow">Claims</span>
          <h2>Test what was advertised</h2>
          <p>Report consistency and uncertainty rather than certainty.</p>
        </article>
      </div>

      <section className="probe-browser">
        <div className="probe-browser-head">
          <div>
            <span className="eyebrow">Probe catalogue</span>
            <h2>Explore the measurement surface</h2>
          </div>
          <label className="search-box">
            <Search size={15} />
            <input
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              placeholder="Search the method"
              aria-label="Search probe families"
            />
          </label>
        </div>
        <div className="filter-row">
          {["All", "Memory", "Isolation", "Claims"].map((option) => (
            <button
              key={option}
              className={group === option ? "filter-current" : ""}
              onClick={() => setGroup(option)}
            >
              {option}
            </button>
          ))}
        </div>
        <div className="probe-public-list">
          {filtered.map((probe) => {
            const isOpen = expanded === probe.section;
            return (
              <article className={"probe-public-row " + (isOpen ? "probe-open" : "")} key={probe.section}>
                <button onClick={() => setExpanded(isOpen ? null : probe.section)} aria-expanded={isOpen}>
                  <span className="probe-public-ref">{probe.section}</span>
                  <span className="probe-public-title">
                    <strong>{probe.title}</strong>
                    <small>{probe.code}</small>
                  </span>
                  <StatusChip tone={probe.availability === "Local GPU" ? "signal" : probe.availability === "Rental needed" ? "amber" : "teal"}>
                    {probe.availability}
                  </StatusChip>
                  <ChevronDown size={16} />
                </button>
                {isOpen && (
                  <div className="probe-detail-public">
                    <p>{probe.summary}</p>
                    <div>
                      <span><CheckCircle2 size={14} /> Implemented</span>
                      <span><ShieldCheck size={14} /> Canary-only boundary</span>
                      <span><Info size={14} /> Limitations reported</span>
                    </div>
                  </div>
                )}
              </article>
            );
          })}
        </div>
      </section>

      <div className="method-links">
        <a href={GITHUB_URL + "/blob/main/docs/methodology.md"} target="_blank" rel="noreferrer">
          <BookOpen size={18} />
          <span><strong>Methodology</strong><small>How a measurement is taken</small></span>
          <ExternalLink size={14} />
        </a>
        <a href={GITHUB_URL + "/blob/main/docs/scoring.md"} target="_blank" rel="noreferrer">
          <BarChart3 size={18} />
          <span><strong>Scoring</strong><small>Why there is no composite score</small></span>
          <ExternalLink size={14} />
        </a>
        <a href={GITHUB_URL + "/blob/main/docs/pre-registration.md"} target="_blank" rel="noreferrer">
          <FileCheck2 size={18} />
          <span><strong>Pre-registration</strong><small>Thresholds fixed before provider data</small></span>
          <ExternalLink size={14} />
        </a>
      </div>
    </div>
  );
}

function ProvidersPage({ navigate }: { navigate: (page: Page) => void }) {
  return (
    <div className="page-frame section-frame">
      <PublicPageHero
        eyebrow="Provider readiness"
        title="Policy is a measurement gate, not paperwork."
        copy="GPU-SEAL does not probe first and ask later. Every provider needs a recorded policy basis or written permission before a rental enters the study."
        icon={Globe2}
      />

      <div className="provider-truth">
        <div className="provider-progress">
          <div className="progress-number"><strong>2</strong><span>/ 4</span></div>
          <div>
            <span className="eyebrow">Pilot policy matrix</span>
            <h2>Two providers are policy-eligible.</h2>
            <p>
              Eligibility does not mean they have been measured. The cloud
              study count remains zero.
            </p>
          </div>
        </div>
        <div className="no-ranking">
          <CloudOff size={22} />
          <span>
            <strong>No provider leaderboard</strong>
            <small>No provider results exist, and the charter forbids composite rankings.</small>
          </span>
        </div>
      </div>

      <div className="public-provider-grid">
        {providers.map((provider) => (
          <article className={"public-provider " + (provider.ready ? "provider-ready" : "provider-pending")} key={provider.code}>
            <div className="provider-head">
              <span className="provider-letter">{provider.code.slice(-1)}</span>
              <span><small>{provider.category}</small><strong>{provider.code}</strong></span>
              <StatusChip tone={provider.ready ? "signal" : "amber"}>{provider.status}</StatusChip>
            </div>
            <div className="provider-class">
              {provider.ready ? <BadgeCheck size={16} /> : <LockKeyhole size={15} />}
              {provider.classification}
            </div>
            <p>{provider.note}</p>
            <div className="provider-facts">
              <span><small>Identity</small><strong>Pseudonymous</strong></span>
              <span><small>Measured</small><strong>No</strong></span>
              <span><small>Policy date</small><strong>03 Aug 2026</strong></span>
            </div>
          </article>
        ))}
      </div>

      <section className="preflight-public">
        <SectionHeader
          eyebrow="Before any provider run"
          title="Seven conditions must be visible."
          copy="The site will never imply a provider scan can begin because one policy row is green."
        />
        <div className="preflight-public-grid">
          {[
            ["Policy reviewed", "Recorded source and date"],
            ["Permission", "Written scope where required"],
            ["Ownership", "Researcher-controlled rental"],
            ["Budget", "Reserved before launch"],
            ["Duration", "Hard ceiling of one hour"],
            ["Hardware", "Probe-specific support"],
            ["Publication", "Manual coordinated release"],
          ].map(([title, note], index) => (
            <div key={String(title)}>
              <span className="gate-neutral">{index + 1}</span>
              <span><strong>{title}</strong><small>{note}</small></span>
            </div>
          ))}
        </div>
      </section>

      <div className="provider-next">
        <div>
          <span className="eyebrow">Want to help?</span>
          <h2>Review policy, contribute a runtime, or reproduce locally.</h2>
        </div>
        <div>
          <a className="secondary-cta" href={GITHUB_URL + "/tree/main/docs/provider-policy-review"} target="_blank" rel="noreferrer">
            Policy records <ExternalLink size={14} />
          </a>
          <button className="primary-cta" onClick={() => navigate("run")}>
            Run locally <ArrowRight size={15} />
          </button>
        </div>
      </div>
    </div>
  );
}

function RunPage({
  copyText,
}: {
  copyText: (value: string, message: string) => Promise<void>;
}) {
  const [selected, setSelected] = useState(runOptions[0]);

  const downloadLauncher = () => {
    downloadText(
      "gpu-seal-" + selected.id + ".ps1",
      [
        "# GPU-SEAL local operation",
        "# Review the project safety policy before execution.",
        selected.command,
        "",
      ].join("\n"),
    );
  };

  return (
    <div className="page-frame section-frame">
      <PublicPageHero
        eyebrow="Run GPU-SEAL"
        title="Start with your own machine."
        copy="The web dashboard cannot access your GPU. It gives you a clear, reviewable path into the open-source local runners."
        icon={SquareTerminal}
      />

      <div className="run-journey">
        <div className="run-steps">
          {[
            ["1", "Clone the repository", "Work from source you can inspect."],
            ["2", "Install the development extras", "Use an isolated Python environment."],
            ["3", "Run the capability smoke check", "Learn what this machine can support."],
            ["4", "Choose a bounded local battery", "Keep real evidence distinct from simulation."],
          ].map(([number, title, note]) => (
            <div className="run-step" key={number}>
              <span>{number}</span>
              <span><strong>{title}</strong><small>{note}</small></span>
            </div>
          ))}
        </div>
        <aside className="requirements-card">
          <span className="eyebrow">What you need</span>
          <h2>Python first. CUDA when available.</h2>
          <ul>
            <li><Check size={13} /> Python 3.10 or newer</li>
            <li><Check size={13} /> Git and an isolated environment</li>
            <li><Info size={13} /> NVIDIA GPU for memory probes</li>
            <li><Info size={13} /> Linux for complete exposure inventory</li>
          </ul>
          <a href={GITHUB_URL + "#five-minute-quickstart"} target="_blank" rel="noreferrer">
            Full quickstart <ExternalLink size={13} />
          </a>
        </aside>
      </div>

      <section className="run-builder-public">
        <div className="run-choice-list">
          <span className="eyebrow">Choose an operation</span>
          {runOptions.map((option) => {
            const Icon = option.icon;
            return (
              <button
                key={option.id}
                className={selected.id === option.id ? "run-choice-current" : ""}
                onClick={() => setSelected(option)}
              >
                <span className="run-choice-icon"><Icon size={18} /></span>
                <span><small>{option.label}</small><strong>{option.title}</strong></span>
                <ChevronRight size={16} />
              </button>
            );
          })}
        </div>

        <div className="run-command-card">
          <div className="run-command-head">
            <div>
              <StatusChip tone="signal">{selected.label}</StatusChip>
              <h2>{selected.title}</h2>
              <p>{selected.description}</p>
            </div>
            <span className="command-output"><FileJson size={15} /> {selected.output}</span>
          </div>
          <div className="command-code">
            <div><span>Repository root</span><Code2 size={14} /></div>
            <code>{selected.command}</code>
          </div>
          <div className="command-actions">
            <button className="secondary-cta" onClick={downloadLauncher}>
              <Download size={15} /> Download launcher
            </button>
            <button className="primary-cta" onClick={() => copyText(selected.command, "Command copied")}>
              <Copy size={15} /> Copy command
            </button>
          </div>
          <div className="run-boundary-note">
            <ShieldCheck size={15} />
            The command is allowlisted and bounded. Cloud launch remains unavailable
            because the repository has no provider runtime adapter.
          </div>
        </div>
      </section>

      <section className="simulation-callout">
        <TriangleAlert size={22} />
        <div>
          <span className="eyebrow">Simulation is a test fixture</span>
          <h2>Never cite a simulated run as provider evidence.</h2>
          <p>
            If CUDA is unavailable, use the explicit simulation flag to exercise
            reporting and safety paths—not to make a claim about hardware.
          </p>
        </div>
        <button
          className="download-button"
          onClick={() => copyText(
            "python lab/local-runner/run_phase1.py --out ./out-simulated --size-mib 32 --cycles 10 --simulate",
            "Simulation command copied",
          )}
        >
          <Clipboard size={14} /> Copy simulation command
        </button>
      </section>
    </div>
  );
}

function SafetyPage({ navigate }: { navigate: (page: Page) => void }) {
  return (
    <div className="page-frame section-frame">
      <PublicPageHero
        eyebrow="Safety & ethics"
        title="The refusal path is part of the result."
        copy="GPU-SEAL is an assurance framework, not an exploitation toolkit. Its safety boundaries are enforced in code and tested to fail closed."
        icon={ShieldCheck}
      />

      <div className="safety-principles">
        {[
          {
            icon: Fingerprint,
            title: "Canary-only search",
            copy: "The probe searches only for cryptographic markers it minted itself.",
            ref: "ETHICS §7.2",
          },
          {
            icon: HardDrive,
            title: "No raw retention",
            copy: "Unknown GPU memory is reduced to allowlisted statistics and discarded.",
            ref: "Data policy",
          },
          {
            icon: Eye,
            title: "No content rendering",
            copy: "Unknown bytes never become text, imagery, or a downloadable payload.",
            ref: "Static gate",
          },
          {
            icon: KeyRound,
            title: "Signed evidence",
            copy: "Every result carries integrity metadata and measurement hashes.",
            ref: "Evidence boundary",
          },
          {
            icon: LockKeyhole,
            title: "Manual publication",
            copy: "A technically safe bundle can still be held for provenance or disclosure.",
            ref: "Disclosure gate",
          },
          {
            icon: Users,
            title: "No public ranking",
            copy: "Independent assurance categories never collapse into a provider leaderboard.",
            ref: "Charter §13",
          },
        ].map((item) => {
          const Icon = item.icon;
          return (
            <article className="safety-public-card" key={item.title}>
              <span className="safety-public-icon"><Icon size={22} /></span>
              <span className="method-ref">{item.ref}</span>
              <h2>{item.title}</h2>
              <p>{item.copy}</p>
              <span className="enforced-label"><CheckCircle2 size={13} /> Enforced</span>
            </article>
          );
        })}
      </div>

      <section className="mutation-proof">
        <div className="mutation-score">
          <strong>38 / 38</strong>
          <span>injected policy violations caught</span>
        </div>
        <div className="mutation-copy">
          <span className="eyebrow">Negative-control battery</span>
          <h2>A green safety suite that cannot fail is decoration.</h2>
          <p>
            GPU-SEAL mutates its own controls with forbidden behaviors and
            requires every one to be rejected. This proves the guardrails are
            observable, not aspirational.
          </p>
          <a href={GITHUB_URL + "/tree/main/tests/safety"} target="_blank" rel="noreferrer">
            Inspect safety tests <ExternalLink size={13} />
          </a>
        </div>
      </section>

      <section className="disclosure-public">
        <SectionHeader
          eyebrow="Responsible disclosure"
          title="Observation is the first step—not the headline."
          copy="A potential provider-sensitive result moves through reproduction, methodology review, ownership confirmation, coordination, and retesting."
        />
        <div className="disclosure-steps">
          {[
            "Observed",
            "Reproduced",
            "Method checked",
            "Ownership confirmed",
            "Provider contacted",
            "Retested",
            "Publication cleared",
          ].map((step, index) => (
            <div key={step}>
              <span>{index + 1}</span>
              <strong>{step}</strong>
            </div>
          ))}
        </div>
        <div className="disclosure-note">
          <LockKeyhole size={16} />
          90-day remediation window plus a 30-day coordination period.
        </div>
      </section>

      <div className="safety-bottom-cta">
        <div>
          <span className="eyebrow">Ready to inspect it?</span>
          <h2>Read the policy. Run the controls. Challenge the method.</h2>
        </div>
        <div>
          <a className="secondary-cta" href={GITHUB_URL + "/blob/main/ETHICS.md"} target="_blank" rel="noreferrer">
            Ethics policy <ExternalLink size={14} />
          </a>
          <button className="primary-cta" onClick={() => navigate("run")}>
            Verify locally <ArrowRight size={15} />
          </button>
        </div>
      </div>
    </div>
  );
}

function PublicPageHero({
  eyebrow,
  title,
  copy,
  icon: Icon,
}: {
  eyebrow: string;
  title: string;
  copy: string;
  icon: LucideIcon;
}) {
  return (
    <section className="public-page-hero enter">
      <div>
        <span className="eyebrow">{eyebrow}</span>
        <h1>{title}</h1>
        <p>{copy}</p>
      </div>
      <span className="page-hero-icon"><Icon size={36} /></span>
    </section>
  );
}

function EvidenceDrawer({
  run,
  onClose,
}: {
  run: EvidenceRun;
  onClose: () => void;
}) {
  const index = {
    run_id: run.id,
    type: run.type,
    measurement_path: run.path,
    probe_records: run.records,
    control: run.control,
    result: run.result,
    integrity: run.integrity,
    publication: run.publication,
    raw_unknown_memory_retained: false,
    unknown_memory_rendered: false,
    canary_only_search: true,
  };

  return (
    <>
      <button className="drawer-backdrop" onClick={onClose} aria-label="Close evidence details" />
      <aside className="evidence-drawer" aria-label="Evidence details">
        <div className="drawer-head">
          <div>
            <span className="eyebrow">Evidence detail</span>
            <h2>{run.title}</h2>
            <code>{run.id}</code>
          </div>
          <button onClick={onClose} aria-label="Close">
            <X size={18} />
          </button>
        </div>

        <div className="drawer-chips">
          <StatusChip tone={run.integrity === "Internally consistent" ? "signal" : "amber"}>
            {run.integrity === "Internally consistent" ? <Check size={11} /> : <TriangleAlert size={11} />}
            {run.integrity}
          </StatusChip>
          <StatusChip tone={run.type === "Simulation fixture" ? "amber" : "teal"}>{run.type}</StatusChip>
          <StatusChip>{run.publication}</StatusChip>
        </div>

        <section className="drawer-section">
          <span className="eyebrow">What this record means</span>
          <p>{run.note}</p>
        </section>

        <div className="drawer-facts">
          <div><small>Timestamp</small><strong>{run.timestamp}</strong></div>
          <div><small>Records</small><strong>{run.records}</strong></div>
          <div><small>Measurement path</small><strong>{run.path}</strong></div>
          <div><small>Control</small><strong>{run.control}</strong></div>
          <div><small>Result</small><strong>{run.result}</strong></div>
          <div><small>Publication</small><strong>{run.publication}</strong></div>
        </div>

        <section className="drawer-section">
          <span className="eyebrow">Trust boundary</span>
          <div className="drawer-callout">
            <KeyRound size={16} />
            <p>
              Internal integrity is not external provenance. This public index
              does not expose a trusted keyring or claim provider validation.
            </p>
          </div>
        </section>

        <section className="drawer-section">
          <span className="eyebrow">Safety assertions</span>
          <div className="assertion-list">
            <span><Check size={12} /> Canary-only search</span>
            <span><Check size={12} /> No raw retention</span>
            <span><Check size={12} /> No unknown-memory rendering</span>
          </div>
        </section>

        <section className="drawer-section drawer-json">
          <div>
            <span className="eyebrow">Public index JSON</span>
            <button onClick={() => downloadText(run.id + ".json", JSON.stringify(index, null, 2), "application/json")}>
              <Download size={13} /> Download
            </button>
          </div>
          <pre>{JSON.stringify(index, null, 2)}</pre>
        </section>
      </aside>
    </>
  );
}

function PublicCta({ navigate }: { navigate: (page: Page) => void }) {
  return (
    <section className="public-cta-wrap section-frame">
      <div className="public-cta">
        <div className="cta-mark">
          <BrandMark />
        </div>
        <div>
          <span className="eyebrow">Open research · reproducible evidence</span>
          <h2>Do not take the provider—or this project—on faith.</h2>
          <p>Inspect the method, run the controls, and contribute what is missing.</p>
        </div>
        <div className="public-cta-actions">
          <a className="secondary-cta" href={GITHUB_URL} target="_blank" rel="noreferrer">
            <GitFork size={15} /> View source
          </a>
          <button className="primary-cta" onClick={() => navigate("run")}>
            Run GPU-SEAL <ArrowRight size={15} />
          </button>
        </div>
      </div>
    </section>
  );
}

function SiteFooter({ navigate }: { navigate: (page: Page) => void }) {
  return (
    <footer className="site-footer">
      <div className="section-frame footer-grid">
        <div className="footer-brand">
          <BrandMark compact />
          <div>
            <strong>GPU-SEAL</strong>
            <span>Ghost Meter</span>
            <p>Evidence before assurance.</p>
          </div>
        </div>
        <div className="footer-links">
          <div>
            <strong>Explore</strong>
            <button onClick={() => navigate("evidence")}>Evidence</button>
            <button onClick={() => navigate("method")}>Method</button>
            <button onClick={() => navigate("providers")}>Providers</button>
          </div>
          <div>
            <strong>Use it</strong>
            <button onClick={() => navigate("run")}>Run locally</button>
            <button onClick={() => navigate("safety")}>Safety</button>
            <a href={GITHUB_URL + "/issues"} target="_blank" rel="noreferrer">Contribute</a>
          </div>
          <div>
            <strong>Project</strong>
            <a href={DOCS_URL} target="_blank" rel="noreferrer">Documentation</a>
            <a href={GITHUB_URL} target="_blank" rel="noreferrer">GitHub</a>
            <a href={GITHUB_URL + "/blob/main/LICENSE"} target="_blank" rel="noreferrer">Apache-2.0</a>
          </div>
        </div>
      </div>
      <div className="section-frame footer-bottom">
        <span>GPU-SEAL is a research assurance framework, not an exploitation toolkit.</span>
        <span>Current phase: local validation · no cloud study yet</span>
      </div>
    </footer>
  );
}
