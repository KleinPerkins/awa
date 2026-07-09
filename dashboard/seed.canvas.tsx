import {
  Stack,
  Row,
  Grid,
  Spacer,
  H1,
  H2,
  H3,
  Text,
  Code,
  Stat,
  Pill,
  Table,
  Callout,
  Button,
  useCanvasState,
  useCanvasAction,
} from "cursor/canvas";

// ---------------------------------------------------------------------------
// AWA — "is your work safe?" status dashboard (GENERIC, data-free seed).
//
// This file is the SOURCE-TRACKED SEED shipped in KleinPerkins/awa. It carries NO machine
// paths and NO org literals: the INITIAL_RAW block below is data-free on purpose. A host/agent
// injects a live dashboard snapshot (awa-worktree/v1) between the AWA_DATA markers and renders
// the populated copy into the Cursor workspace canvases dir.
//
// EGRESS GATE (system-wide operator egress): everything a non-technical operator reads BY DEFAULT
// is authored jargon-free. All static display copy lives in the PM_COPY block (scanned verbatim by
// engine/tests/test_egress_surfaces.py), and every dynamic line is rendered from the emitter's
// jargon-free `plain` / `plain_*` fields (scanned in Python over a real tree). Raw git commands and
// mechanism detail live ONLY in the AGENT_PROMPTS + TECHNICAL blocks below — agent/maintainer-facing,
// shown only behind an explicit "Show technical details" disclosure, and deliberately OUT of the PM
// egress scope. Keeping raw/mechanism text out of the default view is the whole point of the gate.
// ---------------------------------------------------------------------------

type WtStatus = "even" | "ahead" | "behind" | "diverged" | "no-base" | "unknown";
type Classification = "include" | "exclude" | "advisory";
type RepoMode = "on" | "off" | "invalid" | "";

type Worktree = {
  path: string;
  branch: string;
  detached: boolean;
  is_primary: boolean;
  is_linked: boolean;
  locked: boolean;
  prunable: boolean;
  head: string;
  dirty: boolean;
  dirty_count: number;
  ahead: number;
  behind: number;
  ab_status: WtStatus;
  is_base_branch: boolean;
  last_commit_ts: string | null;
  last_commit_subject: string | null;
  // Additive, optional jargon-free operator fields (emitter-authored, egress-scanned in Python).
  plain_status?: string;
  plain_next?: string;
};

type OrphanBranch = {
  branch: string;
  head: string;
  ahead: number;
  behind: number;
  ab_status: WtStatus;
  last_commit_ts: string | null;
  last_commit_subject: string | null;
  plain_status?: string;
  plain_next?: string;
};

type Repo = {
  path: string;
  rel: string;
  name: string;
  classification: Classification;
  reason: string;
  mode?: RepoMode;
  mode_error?: string;
  owner_repo: string;
  has_base: boolean;
  base_ref: string;
  default_base: string;
  branches: string[];
  orphan_branches: OrphanBranch[];
  worktrees: Worktree[];
  plain_next?: string;
};

type Summary = {
  repos: number;
  included: number;
  excluded: number;
  advisory: number;
  worktrees: number;
  linked: number;
  dirty: number;
  ahead_of_main: number;
  behind_main: number;
  diverged: number;
  no_base: number;
  orphan_branches: number;
};

// Emitter-authored honest-confidence block (jargon-free; scanned in Python). Optional/additive.
type PlainSummary = {
  headline?: string;
  checked?: string;
  not_checked?: string;
  watching?: string;
  attention?: string;
};

type Environment = {
  engine?: { running?: boolean; mode?: string; reason?: string; plain?: string };
};

type DashboardData = {
  schema: string;
  generated_at: string | null;
  root: string;
  default_base: string;
  summary: Summary;
  plain?: PlainSummary;
  repos: Repo[];
  environment?: Environment;
};

type RefreshUi = {
  requestedAt: number;
  baselineGeneratedAt: string;
  nonce: number;
};

// >>> PM_COPY_START — every string here is PM-facing and MUST be jargon-free (Tier A/B/C).
// The egress gate (engine/tests/test_egress_surfaces.py) reads this block verbatim and fails on
// any banned term. If you add a PM-facing string to the canvas, add it HERE — never inline.
const PM_COPY = {
  title: "AWA — is your work safe?",
  subtitle:
    "A plain-language view of what I am looking after for you, and anything that needs a look.",
  pillAttention: "needs a look",
  pillClean: "all safe",
  btnRefresh: "Refresh",
  btnRefreshPending: "Refresh asked for",
  btnTechShow: "Show technical details",
  btnTechHide: "Hide technical details",
  btnCancel: "Cancel",
  btnDismiss: "Dismiss",

  honestTitle: "In plain words",
  sectionProtection: "What I am looking after",
  lastLooked: "Last looked",
  nowShowing: "Now showing",
  keptSafe: "kept safe",
  safeCopiesUnit: "safe copies",
  honestHeadlineFallback: "I am looking after your work.",
  honestCheckedFallback:
    "What I checked: I looked at each place your work lives and where each one stands.",
  honestNotCheckedFallback:
    "What I can't promise: this is a snapshot from a moment ago, so it can't show changes made since, and I can only notice a direct change to your original files after it happens — I can't stop that kind of change in advance.",
  honestWatchingFallback: "I step in the moment you try to change something.",

  cardOriginalTitle: "Your original files",
  cardOriginalKept: "kept clean",
  cardOriginalTouched: "a direct change was noticed",
  cardOriginalBody:
    "I keep new work out of your original files until it is safely copied, and I notice if something changes them directly.",
  cardKeepTitle: "Keeping your work",
  cardKeepBody:
    "Before I tidy anything away, I set aside a safety copy — so your work is not lost.",
  cardSideTitle: "Working side by side",
  cardSideBody:
    "Each piece of work gets its own safe copy, so two things in progress never tread on each other.",
  cardWatchTitle: "How closely I am watching",
  cardWatchClose: "watching closely",
  cardWatchStep: "step-in only",
  cardFreshTitle: "How fresh this view is",
  cardFreshStale: "getting old",
  cardFreshFresh: "fresh",
  cardFreshNone: "no view yet",
  cardFreshBodyStale: "This view is getting old — ask me to refresh it for the latest.",
  cardFreshBodyNone: "Ask me to refresh and I will fill this in.",

  emptyTitle: "No view yet",
  emptyBody: "Ask me to refresh and I will take a fresh look at your work and fill this in.",
  refreshPendingTitle: "Refresh asked for",
  refreshPendingBody:
    "I can't look things up from this view on my own — ask me in chat and I will refresh it for you.",
  refreshDoneTitle: "Updated",

  sectionAttention: "Needs a look",
  sectionSteady: "All good",
  sectionLeftover: "Left-over safe copies",
  sectionExcluded: "Projects I leave alone",
  attentionHint:
    "These have unsaved work, work that is not shared yet, or need a quick decision from you.",
  steadyHint: "Nothing to do here — these are up to date.",
  leftoverHint:
    "Safe copies that are not open anywhere right now — usually fine to tidy away after a quick check.",
  excludedHint: "I leave these projects alone — they look after themselves.",

  headersMain: ["Project", "What you were doing", "Where", "Unsaved", "Compared to the shared version", "Last saved", "What to do"],
  headersLeftover: ["Project", "Compared to the shared version", "Last saved", "What to do"],
  headersExcluded: ["Project", "Why", "What to do"],

  roleSafeCopy: "safe copy",
  roleOriginal: "your original folder",
  workUnknown: "your work",
  unsavedNone: "saved",
  unsavedSome: "unsaved",

  vsOnShared: "this is the shared version",
  vsEven: "up to date",
  vsNone: "nothing to compare to yet",
  vsUnknown: "couldn't check in time",
  vsAhead: "ready to share",
  vsBehind: "to catch up on",
  vsDiverged: "moved apart",

  statProjects: "Projects looked after",
  statProtected: "Protected",
  statCopies: "Safe copies",
  statUnsaved: "With unsaved work",
  statLeftover: "Left-over copies",

  nextFallback: "Nothing to do.",
  statusFallback: "Your work is safe.",
  umbrella: "(top-level folder)",
  noOrigin: "(not linked to a shared home yet)",
} as const;
// <<< PM_COPY_END

// >>> AGENT_PROMPTS_START — agent-facing instructions (NOT PM display copy). Excluded from the PM
// egress scope: these are messages the canvas hands to an agent/chat to act on, not text the
// operator is meant to read as guidance.
const AGENT_PROMPTS = {
  refresh:
    "Refresh the AWA worktree dashboard: run `dev-worktree.sh dashboard-data`, inject the snapshot between the AWA_DATA markers, and report the new snapshot time.",
} as const;
// <<< AGENT_PROMPTS_END

// >>> TECHNICAL_RAW_START — raw git / mechanism detail for engineers. Shown ONLY behind the explicit
// "Show technical details" disclosure, and deliberately OUT of the PM egress scope (the PM default
// view never shows these). This is where Tier A/B terms are allowed to live.
const REFRESH_COMMAND = "dev-worktree.sh dashboard-data";

const SCOPES: { surface: string; state: string; detail: string }[] = [
  {
    surface: "Desktop",
    state: "shell gate + edit detection",
    detail: "beforeShellExecution asks before primary-checkout mutations; afterFileEdit records a detection receipt (cannot pre-block).",
  },
  {
    surface: "Cloud",
    state: "project hooks verified",
    detail: "Committed beforeShellExecution + afterFileEdit + beforeReadFile; failClosed false; PR-first for publish.",
  },
  {
    surface: "CLI",
    state: "dev-worktree verbs",
    detail: "ensure / clean (bundle-or-refuse) / status / doctor deliver the kernel guarantee with the engine off.",
  },
];

function technicalRaw(wt: Worktree): string {
  if (wt.dirty) return "git -C <path> status  # review/commit before cleanup";
  if (wt.detached) return "git -C <path> switch -c <branch>";
  if (wt.locked) return "git worktree unlock <path>  # after confirming why";
  if (wt.prunable) return "git worktree prune";
  if (wt.ab_status === "no-base") return "git fetch origin main:main";
  if (wt.ab_status === "diverged") return "git rebase main  # then push / PR";
  if (wt.ahead > 0) return "git push -u origin <branch>  # or open a PR";
  if (wt.behind > 0) return "git merge --ff-only main";
  return wt.is_linked ? "dev-worktree.sh clean --path <path>" : "dev-worktree.sh ensure";
}

function technicalWhere(wt: Worktree): string {
  const b = wt.branch || (wt.detached ? "(detached HEAD)" : "?");
  return `${b}${wt.head ? " @ " + wt.head : ""}`;
}
// <<< TECHNICAL_RAW_END

// >>> AWA_DATA_START — replaced by the host/agent dashboard injector; keep data-free in git
const INITIAL_RAW = {
  "schema": "awa-worktree/v1",
  "generated_at": null,
  "root": "",
  "default_base": "main",
  "summary": {
    "repos": 0,
    "included": 0,
    "excluded": 0,
    "advisory": 0,
    "worktrees": 0,
    "linked": 0,
    "dirty": 0,
    "ahead_of_main": 0,
    "behind_main": 0,
    "diverged": 0,
    "no_base": 0,
    "orphan_branches": 0
  },
  "repos": []
} as unknown as DashboardData;
// <<< AWA_DATA_END

const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

function formatTs(iso: string | null): string {
  if (!iso) return "never";
  const t = Date.parse(iso);
  if (Number.isNaN(t)) return iso;
  const d = new Date(t);
  const mon = MONTHS[d.getUTCMonth()];
  const day = d.getUTCDate();
  const hh = String(d.getUTCHours()).padStart(2, "0");
  const mm = String(d.getUTCMinutes()).padStart(2, "0");
  return `${mon} ${day} ${hh}:${mm} UTC`;
}

function snapshotAgeHours(iso: string | null): number {
  if (!iso) return Infinity;
  const t = Date.parse(iso);
  if (Number.isNaN(t)) return 0;
  return (Date.now() - t) / 3_600_000;
}

function ageLabel(iso: string | null): string {
  const hours = snapshotAgeHours(iso);
  if (!Number.isFinite(hours)) return "no view yet";
  const mins = Math.round(hours * 60);
  if (mins < 1) return "just now";
  if (mins < 60) return `${mins}m ago`;
  if (hours < 48) return `${Math.round(hours)}h ago`;
  return `${Math.round(hours / 24)}d ago`;
}

function needsAttention(wt: Worktree): boolean {
  return (
    wt.dirty ||
    wt.ahead > 0 ||
    wt.behind > 0 ||
    wt.detached ||
    wt.ab_status === "no-base" ||
    wt.ab_status === "unknown" ||
    wt.locked ||
    wt.prunable
  );
}

// Plain, jargon-free "compared to the shared version" cell label (short form of the emitter data).
function vsLabel(wt: Worktree): string {
  if (wt.ab_status === "no-base") return PM_COPY.vsNone;
  if (wt.ab_status === "unknown") return PM_COPY.vsUnknown;
  if (wt.ab_status === "even") return wt.is_base_branch ? PM_COPY.vsOnShared : PM_COPY.vsEven;
  const parts: string[] = [];
  if (wt.ahead > 0) parts.push(`${wt.ahead} ${PM_COPY.vsAhead}`);
  if (wt.behind > 0) parts.push(`${wt.behind} ${PM_COPY.vsBehind}`);
  if (wt.ab_status === "diverged" && parts.length === 0) parts.push(PM_COPY.vsDiverged);
  return parts.join(" · ") || PM_COPY.vsEven;
}

function orphanVsLabel(b: OrphanBranch): string {
  if (b.ab_status === "no-base") return PM_COPY.vsNone;
  if (b.ab_status === "unknown") return PM_COPY.vsUnknown;
  if (b.ab_status === "even") return PM_COPY.vsEven;
  const parts: string[] = [];
  if (b.ahead > 0) parts.push(`${b.ahead} ${PM_COPY.vsAhead}`);
  if (b.behind > 0) parts.push(`${b.behind} ${PM_COPY.vsBehind}`);
  return parts.join(" · ") || PM_COPY.vsEven;
}

function wtNext(wt: Worktree): string {
  return wt.plain_next || PM_COPY.nextFallback;
}

function roleLabel(wt: Worktree): string {
  return wt.is_linked ? PM_COPY.roleSafeCopy : PM_COPY.roleOriginal;
}

type WtRow = { repo: Repo; wt: Worktree };

function collectWorktrees(repos: Repo[], predicate: (r: Repo) => boolean): WtRow[] {
  const rows: WtRow[] = [];
  for (const repo of repos) {
    if (!predicate(repo)) continue;
    for (const wt of repo.worktrees) rows.push({ repo, wt });
  }
  return rows;
}

function repoModeBadges(repo: Repo) {
  const badges: any[] = [];
  if (repo.mode === "invalid" || repo.mode_error) {
    badges.push(<Pill key="invalid" size="sm">setting needs a fix</Pill>);
  }
  return badges.length ? badges : null;
}

function worktreeRows(rows: WtRow[], showTech: boolean) {
  return rows.map(({ repo, wt }) => [
    <Stack gap={2}>
      <Row gap={6} align="center">
        <Text weight="semibold">{repo.rel === "." ? PM_COPY.umbrella : repo.rel}</Text>
        {repoModeBadges(repo)}
      </Row>
      <Text size="small" tone="quaternary">{repo.owner_repo || PM_COPY.noOrigin}</Text>
    </Stack>,
    <Stack gap={2}>
      <Text size="small" tone="secondary">{wt.last_commit_subject || PM_COPY.workUnknown}</Text>
      {showTech ? <Code>{technicalWhere(wt)}</Code> : null}
    </Stack>,
    <Pill size="sm" active={wt.is_linked}>{roleLabel(wt)}</Pill>,
    wt.dirty
      ? <Pill size="sm" active>{wt.dirty_count} {PM_COPY.unsavedSome}</Pill>
      : <Text size="small" tone="quaternary">{PM_COPY.unsavedNone}</Text>,
    <Text size="small" tone="secondary">{vsLabel(wt)}</Text>,
    <Text size="small" tone="secondary">{formatTs(wt.last_commit_ts)}</Text>,
    <Stack gap={2}>
      <Text size="small" tone="secondary">{wtNext(wt)}</Text>
      {showTech ? <Code>{technicalRaw(wt)}</Code> : null}
    </Stack>,
  ]);
}

function StatusCard({
  title,
  badge,
  active,
  children,
}: {
  title: string;
  badge?: string;
  active?: boolean;
  children: any;
}) {
  return (
    <Stack gap={6} style={{ padding: 14, borderRadius: 10, border: "1px solid rgba(128,128,128,0.22)" }}>
      <Row align="center" gap={8}>
        <Text weight="semibold">{title}</Text>
        <Spacer />
        {badge ? <Pill size="sm" active={!!active}>{badge}</Pill> : null}
      </Row>
      {children}
    </Stack>
  );
}

export default function AwaWorktreeDashboard() {
  const dispatch = useCanvasAction();
  const raw = INITIAL_RAW;
  const [refreshUi, setRefreshUi] = useCanvasState<RefreshUi>("awa.refreshUi", {
    requestedAt: 0,
    baselineGeneratedAt: "",
    nonce: 0,
  });
  const [showTech, setShowTech] = useCanvasState<boolean>("awa.showTech", false);

  const populated = raw.repos.length > 0 && !!raw.generated_at;
  const refreshPending =
    refreshUi.requestedAt > 0 && (raw.generated_at ?? "") === refreshUi.baselineGeneratedAt;
  const refreshSucceeded =
    refreshUi.requestedAt > 0 && (raw.generated_at ?? "") !== refreshUi.baselineGeneratedAt;
  const staleSnapshot = populated && snapshotAgeHours(raw.generated_at) > 1;

  const refreshInChat = () =>
    dispatch({ type: "newComposerChat", userPrompt: AGENT_PROMPTS.refresh });
  const onRefresh = () => {
    setRefreshUi({
      requestedAt: Date.now(),
      baselineGeneratedAt: raw.generated_at ?? "",
      nonce: refreshUi.nonce + 1,
    });
    refreshInChat();
  };
  const onDismissRefresh = () => {
    setRefreshUi({ requestedAt: 0, baselineGeneratedAt: "", nonce: refreshUi.nonce });
  };

  const governed = raw.repos.filter((r) => r.classification !== "exclude");
  const excluded = raw.repos.filter((r) => r.classification === "exclude");
  const attention = collectWorktrees(governed, () => true).filter((row) => needsAttention(row.wt));
  const steady = collectWorktrees(governed, () => true).filter((row) => !needsAttention(row.wt));
  const orphanRows = governed.flatMap((repo) => repo.orphan_branches.map((branch) => ({ repo, branch })));
  const hasAttention = attention.length > 0;

  const plain = raw.plain ?? {};
  const engineInfo = raw.environment?.engine;
  const engineRunning = engineInfo?.running ?? false;
  const includedPrimaries = collectWorktrees(governed, () => true).filter((r) => !r.wt.is_linked);
  const mainEdited = includedPrimaries.some((r) => r.wt.dirty);
  const preservedCount =
    collectWorktrees(governed, () => true).filter((r) => r.wt.ahead > 0).length +
    orphanRows.filter((o) => o.branch.ahead > 0).length;
  const isolatedCount = raw.summary.linked;

  return (
    <Stack gap={20} style={{ padding: 24, maxWidth: 1120 }}>
      <Stack gap={4}>
        <Row align="center">
          <H1>{PM_COPY.title}</H1>
          <Spacer />
          <Button variant="secondary" onClick={() => setShowTech(!showTech)}>
            {showTech ? PM_COPY.btnTechHide : PM_COPY.btnTechShow}
          </Button>
          <Button variant="secondary" disabled={refreshPending} onClick={onRefresh}>
            {refreshPending ? PM_COPY.btnRefreshPending : PM_COPY.btnRefresh}
          </Button>
          <Pill active={!hasAttention}>{hasAttention ? PM_COPY.pillAttention : PM_COPY.pillClean}</Pill>
        </Row>
        <Text tone="secondary">{PM_COPY.subtitle}</Text>
        {populated ? (
          <Text size="small" tone="tertiary">
            {PM_COPY.lastLooked} {formatTs(raw.generated_at)} ({ageLabel(raw.generated_at)})
            {refreshUi.nonce > 0 ? <> · #{refreshUi.nonce}</> : null}
          </Text>
        ) : null}
      </Stack>

      {/* Honest confidence — what I checked and what I can't promise (emitter-authored, jargon-free). */}
      <Stack gap={6} style={{ padding: 14, borderRadius: 10, border: "1px solid rgba(128,128,128,0.22)" }}>
        <Text weight="semibold">{PM_COPY.honestTitle}</Text>
        <Text tone="secondary">{plain.headline || PM_COPY.honestHeadlineFallback}</Text>
        <Text size="small" tone="tertiary">{plain.checked || PM_COPY.honestCheckedFallback}</Text>
        <Text size="small" tone="tertiary">{plain.not_checked || PM_COPY.honestNotCheckedFallback}</Text>
        <Text size="small" tone="tertiary">{plain.watching || engineInfo?.plain || PM_COPY.honestWatchingFallback}</Text>
      </Stack>

      {!populated ? (
        <Callout tone="info" title={PM_COPY.emptyTitle}>
          {PM_COPY.emptyBody}
        </Callout>
      ) : null}

      {refreshPending ? (
        <Callout tone="info" title={PM_COPY.refreshPendingTitle}>
          {PM_COPY.refreshPendingBody}
          <Row gap={8} wrap style={{ marginTop: 8 }}>
            <Button variant="secondary" onClick={refreshInChat}>{PM_COPY.btnRefresh}</Button>
            <Button variant="secondary" onClick={onDismissRefresh}>{PM_COPY.btnCancel}</Button>
          </Row>
        </Callout>
      ) : null}

      {refreshSucceeded ? (
        <Callout tone="success" title={PM_COPY.refreshDoneTitle}>
          {`${PM_COPY.nowShowing} ${formatTs(raw.generated_at)}.`}
          <Row gap={8} wrap style={{ marginTop: 8 }}>
            <Button variant="secondary" onClick={onDismissRefresh}>{PM_COPY.btnDismiss}</Button>
          </Row>
        </Callout>
      ) : null}

      <Stack gap={8}>
        <H2>{PM_COPY.sectionProtection}</H2>
        <Grid columns="repeat(auto-fit, minmax(240px, 1fr))" gap={12}>
          <StatusCard title={PM_COPY.cardOriginalTitle} badge={mainEdited ? PM_COPY.cardOriginalTouched : PM_COPY.cardOriginalKept} active={!mainEdited}>
            <Text size="small" tone="secondary">{PM_COPY.cardOriginalBody}</Text>
          </StatusCard>
          <StatusCard title={PM_COPY.cardKeepTitle} badge={`${preservedCount} ${PM_COPY.keptSafe}`} active={preservedCount > 0}>
            <Text size="small" tone="secondary">{PM_COPY.cardKeepBody}</Text>
          </StatusCard>
          <StatusCard title={PM_COPY.cardSideTitle} badge={`${isolatedCount} ${PM_COPY.safeCopiesUnit}`} active>
            <Text size="small" tone="secondary">{PM_COPY.cardSideBody}</Text>
          </StatusCard>
        </Grid>
        <Grid columns="repeat(auto-fit, minmax(240px, 1fr))" gap={12}>
          <StatusCard title={PM_COPY.cardWatchTitle} badge={engineRunning ? PM_COPY.cardWatchClose : PM_COPY.cardWatchStep} active={engineRunning}>
            <Text size="small" tone="secondary">{plain.watching || engineInfo?.plain || PM_COPY.honestWatchingFallback}</Text>
          </StatusCard>
          <StatusCard
            title={PM_COPY.cardFreshTitle}
            badge={staleSnapshot ? PM_COPY.cardFreshStale : populated ? PM_COPY.cardFreshFresh : PM_COPY.cardFreshNone}
            active={!staleSnapshot && populated}
          >
            <Text size="small" tone="secondary">
              {populated ? PM_COPY.cardFreshBodyStale : PM_COPY.cardFreshBodyNone}
            </Text>
          </StatusCard>
        </Grid>
        {showTech ? (
          <Grid columns="repeat(auto-fit, minmax(240px, 1fr))" gap={12}>
            {SCOPES.map((s) => (
              <StatusCard key={s.surface} title={`Scope · ${s.surface}`} badge={s.state}>
                <Text size="small" tone="secondary">{s.detail}</Text>
              </StatusCard>
            ))}
          </Grid>
        ) : null}
      </Stack>

      {populated ? (
        <Grid columns="repeat(auto-fit, minmax(124px, 1fr))" gap={12}>
          <Stat value={raw.summary.repos} label={PM_COPY.statProjects} />
          <Stat value={raw.summary.included} label={PM_COPY.statProtected} tone="info" />
          <Stat value={raw.summary.linked} label={PM_COPY.statCopies} tone={raw.summary.linked ? "info" : "success"} />
          <Stat value={raw.summary.dirty} label={PM_COPY.statUnsaved} tone={raw.summary.dirty ? "warning" : "success"} />
          <Stat value={raw.summary.orphan_branches} label={PM_COPY.statLeftover} tone={raw.summary.orphan_branches ? "warning" : "success"} />
        </Grid>
      ) : null}

      {hasAttention ? (
        <Stack gap={8}>
          <Row align="center" gap={8}>
            <H2>{PM_COPY.sectionAttention}</H2>
            <Pill size="sm" active>{attention.length}</Pill>
          </Row>
          <Text size="small" tone="tertiary">{PM_COPY.attentionHint}</Text>
          <Table
            headers={PM_COPY.headersMain}
            rows={worktreeRows(attention, showTech)}
            rowTone={attention.map(() => "warning" as const)}
            striped
          />
        </Stack>
      ) : null}

      {steady.length > 0 ? (
        <Stack gap={8}>
          <H2>{PM_COPY.sectionSteady}</H2>
          <Text size="small" tone="tertiary">{PM_COPY.steadyHint}</Text>
          <Table
            headers={PM_COPY.headersMain}
            rows={worktreeRows(steady, showTech)}
            rowTone={steady.map(() => "success" as const)}
            striped
          />
        </Stack>
      ) : null}

      {orphanRows.length > 0 ? (
        <Stack gap={8}>
          <Row align="center" gap={8}>
            <H2>{PM_COPY.sectionLeftover}</H2>
            <Pill size="sm" active>{orphanRows.length}</Pill>
          </Row>
          <Text size="small" tone="tertiary">{PM_COPY.leftoverHint}</Text>
          <Table
            headers={PM_COPY.headersLeftover}
            rows={orphanRows.map(({ repo, branch }) => [
              <Text weight="semibold">{repo.rel === "." ? PM_COPY.umbrella : repo.rel}</Text>,
              <Text size="small" tone="secondary">{orphanVsLabel(branch)}</Text>,
              <Text size="small" tone="secondary">{formatTs(branch.last_commit_ts)}</Text>,
              <Text size="small" tone="secondary">{branch.plain_next || PM_COPY.nextFallback}</Text>,
            ])}
            rowTone={orphanRows.map(() => "warning" as const)}
            striped
          />
        </Stack>
      ) : null}

      {excluded.length > 0 ? (
        <Stack gap={8}>
          <H3>{PM_COPY.sectionExcluded}</H3>
          <Text size="small" tone="tertiary">{PM_COPY.excludedHint}</Text>
          <Table
            headers={PM_COPY.headersExcluded}
            rows={excluded.map((r) => [
              <Stack gap={2}>
                <Text weight="semibold">{r.rel === "." ? PM_COPY.umbrella : r.rel}</Text>
                <Text size="small" tone="quaternary">{r.owner_repo || PM_COPY.noOrigin}</Text>
              </Stack>,
              <Text size="small">{r.reason}</Text>,
              <Text size="small" tone="secondary">{r.plain_next || PM_COPY.excludedHint}</Text>,
            ])}
          />
        </Stack>
      ) : null}
    </Stack>
  );
}
