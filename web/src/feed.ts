import {
  DEFAULT_TRACKING,
  type FeedPayload,
  type Job,
  type RawJob,
  type RawSearch,
  type Run,
  type Search,
  type Settings,
  type SortKey,
} from "./types";

function str(value: unknown): string {
  return typeof value === "string" ? value : value == null ? "" : String(value);
}

function num(value: unknown): number {
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : 0;
}

export function slug(value: string): string {
  return (
    value
      .toLowerCase()
      .replace(/[^a-z0-9]+/g, "-")
      .replace(/^-+|-+$/g, "") || "search"
  );
}

export function normalizeJob(raw: RawJob, existing?: Job): Job | null {
  const id = str(raw.id);
  if (!id) return null;
  const pick = (snake: string, camel: string): unknown => raw[snake] ?? raw[camel];
  const existingTracking = existing?.tracking ?? DEFAULT_TRACKING;
  const incomingTracking = (raw as Record<string, unknown>).tracking as
    | Partial<Job["tracking"]>
    | undefined;
  const tracking = incomingTracking
    ? {
        ...DEFAULT_TRACKING,
        ...incomingTracking,
        tags: [...(incomingTracking.tags ?? [])],
        updatedAt: incomingTracking.updatedAt ?? "",
      }
    : {
        ...existingTracking,
        tags: [...(existingTracking.tags ?? [])],
      };
  return {
    id,
    title: str(raw.title) || "Untitled job",
    company: str(raw.company),
    companyId: str(pick("company_id", "companyId")),
    location: str(raw.location),
    salary: str(raw.salary),
    listingDate: str(pick("listing_date", "listingDate")),
    listingDateDisplay: str(pick("listing_date_display", "listingDateDisplay")),
    postedDisplay: str(pick("posted_display", "postedDisplay")),
    teaser: str(raw.teaser),
    workTypes: str(pick("work_types", "workTypes")),
    workArrangement: str(pick("work_arrangement", "workArrangement")),
    classification: str(raw.classification),
    subclassification: str(raw.subclassification),
    url: str(raw.url),
    roleId: str(pick("role_id", "roleId")),
    isFeatured: Boolean(pick("is_featured", "isFeatured")),
    isVerified: pick("is_verified", "isVerified") == null ? null : Boolean(pick("is_verified", "isVerified")),
    isLinkOut: pick("is_link_out", "isLinkOut") == null ? null : Boolean(pick("is_link_out", "isLinkOut")),
    descriptionHtml: str(pick("description_html", "descriptionHtml")),
    descriptionText: str(pick("description_text", "descriptionText")),
    expiresAt: str(pick("expires_at", "expiresAt")),
    applyUrl: str(pick("apply_url", "applyUrl")),
    searchName: str(pick("search_name", "searchName")) || existing?.searchName || "",
    firstSeen:
      str(pick("first_seen", "firstSeen")) || existing?.firstSeen || new Date().toISOString(),
    lastSeen:
      str(pick("last_seen", "lastSeen")) || existing?.lastSeen || new Date().toISOString(),
    isNew: existing?.isNew ?? false,
    tracking,
  };
}

export function normalizeSearch(raw: RawSearch | Record<string, unknown>): Search {
  const data = raw as Record<string, unknown>;
  const keywords = str(data.keywords);
  const where = str(data.where);
  const name = str(data.name) || slug(`${keywords}-${where}`);
  const daterange = data.daterange == null || data.daterange === "" ? null : num(data.daterange);
  return {
    name,
    keywords,
    where,
    sort: str(data.sort) || "Relevance",
    daterange: daterange && daterange > 0 ? daterange : null,
    worktype: str(data.worktype),
    pageSize: Math.max(1, Math.min(num(data.page_size ?? data.pageSize) || 30, 100)),
    maxPages: Math.max(1, num(data.max_pages ?? data.maxPages) || 3),
    maxJobs: Math.max(0, num(data.max_jobs ?? data.maxJobs)),
    enrich: data.enrich == null ? true : Boolean(data.enrich),
    enabled: data.enabled == null ? true : Boolean(data.enabled),
    notifyOnFirstRun: Boolean(data.notify_on_first_run ?? data.notifyOnFirstRun),
  };
}

export function normalizeRun(raw: Record<string, unknown>): Run {
  const startedAt = str(raw.started_at ?? raw.startedAt);
  const id = num(raw.id);
  return {
    key: `${startedAt}::${id}`,
    id,
    startedAt,
    finishedAt: raw.finished_at ? str(raw.finished_at) : null,
    searches: num(raw.searches),
    scanned: num(raw.scanned),
    newJobs: num(raw.new_jobs ?? raw.newJobs),
    notified: num(raw.notified),
    errors: num(raw.errors),
  };
}

export interface MergeResult {
  jobs: Job[];
  added: Job[];
  updated: number;
  searches: Search[];
  runs: Run[];
  importedSearches: number;
  generatedAt: string;
}

export interface MergeOptions {
  importSearches?: boolean;
  markNew?: boolean;
  baseline?: boolean;
}

export function parseFeedPayload(input: unknown): FeedPayload {
  if (Array.isArray(input)) return { jobs: input as RawJob[] };
  if (input && typeof input === "object") {
    const obj = input as Record<string, unknown>;
    if (Array.isArray(obj.jobs)) return obj as FeedPayload;
    if (typeof obj.id === "string") return { jobs: [obj as RawJob] };
  }
  throw new Error("Unrecognised feed format: expected a feed object, a job array, or JSONL.");
}

export function parseFeedText(text: string): FeedPayload {
  const trimmed = text.trim();
  if (!trimmed) throw new Error("The file or response is empty.");
  try {
    return parseFeedPayload(JSON.parse(trimmed));
  } catch (error) {
    if (error instanceof SyntaxError) {
      const jobs: RawJob[] = [];
      for (const [index, line] of trimmed.split(/\r?\n/).entries()) {
        if (!line.trim()) continue;
        try {
          jobs.push(JSON.parse(line) as RawJob);
        } catch {
          throw new Error(`Invalid JSON on line ${index + 1}.`);
        }
      }
      if (jobs.length) return { jobs };
    }
    throw error;
  }
}

export function mergeFeed(
  payload: FeedPayload,
  existingJobs: Job[],
  existingSearches: Search[],
  options: MergeOptions = {},
): MergeResult {
  const existingById = new Map(existingJobs.map((job) => [job.id, job]));
  const baseline = options.baseline ?? existingJobs.length === 0;
  const markNew = options.markNew ?? true;
  const jobs: Job[] = [];
  const added: Job[] = [];
  const seenIds = new Set<string>();
  let updated = 0;

  for (const raw of payload.jobs ?? []) {
    const existing = existingById.get(str(raw.id));
    const job = normalizeJob(raw, existing);
    if (!job) continue;
    seenIds.add(job.id);
    if (!existing) {
      job.isNew = markNew && !baseline;
      added.push(job);
    } else {
      updated += 1;
    }
    jobs.push(job);
  }
  // Keep local jobs that the feed did not include (older snapshots, manual imports).
  for (const job of existingJobs) {
    if (!seenIds.has(job.id)) jobs.push(job);
  }

  const existingByName = new Map(existingSearches.map((search) => [search.name, search]));
  const shouldImport = options.importSearches ?? existingSearches.length === 0;
  const searches = shouldImport
    ? (payload.searches ?? [])
        .map(normalizeSearch)
        .filter((search) => search.keywords || search.where)
    : [...existingSearches];
  const importedSearches = shouldImport
    ? searches.filter((search) => existingByName.get(search.name) == null).length
    : 0;

  const runs = (payload.runs ?? []).map(normalizeRun);

  return {
    jobs,
    added,
    updated,
    searches,
    runs,
    importedSearches,
    generatedAt: payload.generated_at ? String(payload.generated_at) : new Date().toISOString(),
  };
}

export async function fetchFeedText(url: string): Promise<string> {
  const response = await fetch(url, { cache: "no-store" });
  if (!response.ok) {
    throw new Error(`Feed request failed: HTTP ${response.status} ${response.statusText}`);
  }
  return response.text();
}

export function tomlString(value: string): string {
  return JSON.stringify(value);
}

export function searchesToToml(searches: Search[]): string {
  const lines = [
    "# Generated by the JobStreetracer PWA.",
    "# Paste these blocks into config.toml, or replace its [[search]] blocks.",
    "",
  ];
  if (searches.length === 0) lines.push("# No saved searches yet.");
  for (const search of searches) {
    lines.push("[[search]]", `name = ${tomlString(search.name)}`);
    lines.push(`keywords = ${tomlString(search.keywords)}`);
    lines.push(`where = ${tomlString(search.where)}`);
    lines.push(`sort = ${tomlString(search.sort)}`);
    if (search.daterange) lines.push(`daterange = ${search.daterange}`);
    if (search.worktype) lines.push(`worktype = ${tomlString(search.worktype)}`);
    lines.push(`page_size = ${search.pageSize}`);
    lines.push(`max_pages = ${search.maxPages}`);
    if (search.maxJobs) lines.push(`max_jobs = ${search.maxJobs}`);
    lines.push(`enrich = ${search.enrich}`);
    lines.push(`enabled = ${search.enabled}`);
    if (search.notifyOnFirstRun) lines.push("notify_on_first_run = true");
    lines.push("");
  }
  return lines.join("\n");
}

export function exportBackup(
  jobs: Job[],
  searches: Search[],
  runs: Run[],
  settings: Settings,
  includeSecrets: boolean,
): string {
  const safeSettings: Settings = {
    ...settings,
    telegram: includeSecrets ? settings.telegram : { token: "", chatIds: "", topicId: "" },
  };
  return JSON.stringify(
    {
      schema: 1,
      generated_at: new Date().toISOString(),
      source: "jobstreetracer-pwa",
      searches,
      jobs,
      runs,
      settings: safeSettings,
    },
    null,
    2,
  );
}

export function downloadText(filename: string, text: string, type = "application/json"): void {
  const blob = new Blob([text], { type });
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = filename;
  anchor.click();
  URL.revokeObjectURL(url);
}

export function matchesText(job: Job, query: string): boolean {
  if (!query.trim()) return true;
  const needle = query.trim().toLowerCase();
  const haystack = [
    job.title,
    job.company,
    job.location,
    job.salary,
    job.classification,
    job.subclassification,
    job.workTypes,
    job.workArrangement,
    job.searchName,
    job.teaser,
    job.descriptionText.slice(0, 4000),
    job.tracking.tags.join(" "),
    job.tracking.notes,
  ]
    .join(" ")
    .toLowerCase();
  return haystack.includes(needle);
}

export function parseSalary(value: string): number {
  const lower = value.toLowerCase();
  if (!lower || /negotiable|competitiv|confidential/.test(lower)) return 0;
  const matches = lower.match(/\d[\d.,]*/g);
  if (!matches) return 0;
  let best = 0;
  for (const match of matches) {
    let cleaned = match;
    if (cleaned.includes(".") && cleaned.includes(",")) {
      cleaned = cleaned.replace(/\./g, "").replace(/,/g, ".");
    } else if (cleaned.includes(".")) {
      cleaned = cleaned.replace(/\./g, "");
    } else if (cleaned.includes(",")) {
      const parts = cleaned.split(",");
      cleaned = parts[parts.length - 1].length === 3 ? cleaned.replace(/,/g, "") : cleaned.replace(",", ".");
    }
    const number = Number.parseFloat(cleaned);
    if (Number.isFinite(number)) best = Math.max(best, number);
  }
  if (lower.includes("juta") || lower.includes("jt")) best *= 1_000_000;
  else if (lower.includes("mio") || lower.includes("million")) best *= 1_000_000;
  return best;
}

export function sortJobs(jobs: Job[], sort: SortKey): Job[] {
  const sorted = [...jobs];
  const time = (value: string): number => {
    const parsed = Date.parse(value);
    return Number.isNaN(parsed) ? 0 : parsed;
  };
  switch (sort) {
    case "oldest":
      sorted.sort((a, b) => time(a.firstSeen) - time(b.firstSeen));
      break;
    case "title":
      sorted.sort((a, b) => a.title.localeCompare(b.title));
      break;
    case "company":
      sorted.sort((a, b) => a.company.localeCompare(b.company) || a.title.localeCompare(b.title));
      break;
    case "salary":
      sorted.sort((a, b) => parseSalary(b.salary) - parseSalary(a.salary));
      break;
    default:
      sorted.sort((a, b) => time(b.firstSeen) - time(a.firstSeen) || time(b.listingDate) - time(a.listingDate));
  }
  return sorted;
}

export function formatDate(value: string): string {
  if (!value) return "—";
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return value;
  return new Intl.DateTimeFormat("en-ID", {
    day: "2-digit",
    month: "short",
    year: "numeric",
  }).format(parsed);
}

export function relativeTime(value: string): string {
  if (!value) return "never";
  const parsed = new Date(value).getTime();
  if (Number.isNaN(parsed)) return value;
  const diff = Date.now() - parsed;
  const minutes = Math.round(diff / 60_000);
  if (minutes < 1) return "just now";
  if (minutes < 60) return `${minutes}m ago`;
  const hours = Math.round(minutes / 60);
  if (hours < 24) return `${hours}h ago`;
  const days = Math.round(hours / 24);
  if (days < 31) return `${days}d ago`;
  return formatDate(value);
}
