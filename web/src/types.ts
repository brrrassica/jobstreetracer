export type JobStatus =
  | "inbox"
  | "shortlisted"
  | "applied"
  | "interview"
  | "offer"
  | "rejected"
  | "archived";

export const JOB_STATUSES: JobStatus[] = [
  "inbox",
  "shortlisted",
  "applied",
  "interview",
  "offer",
  "rejected",
  "archived",
];

export const STATUS_LABELS: Record<JobStatus, string> = {
  inbox: "Inbox",
  shortlisted: "Shortlisted",
  applied: "Applied",
  interview: "Interview",
  offer: "Offer",
  rejected: "Rejected",
  archived: "Archived",
};

export interface Tracking {
  status: JobStatus;
  notes: string;
  tags: string[];
  seen: boolean;
  updatedAt: string;
}

export interface Job {
  id: string;
  title: string;
  company: string;
  companyId: string;
  location: string;
  salary: string;
  listingDate: string;
  listingDateDisplay: string;
  postedDisplay: string;
  teaser: string;
  workTypes: string;
  workArrangement: string;
  classification: string;
  subclassification: string;
  url: string;
  roleId: string;
  isFeatured: boolean;
  isVerified: boolean | null;
  isLinkOut: boolean | null;
  descriptionHtml: string;
  descriptionText: string;
  expiresAt: string;
  applyUrl: string;
  searchName: string;
  firstSeen: string;
  lastSeen: string;
  isNew: boolean;
  tracking: Tracking;
}

export interface Search {
  name: string;
  keywords: string;
  where: string;
  sort: string;
  daterange: number | null;
  worktype: string;
  pageSize: number;
  maxPages: number;
  maxJobs: number;
  enrich: boolean;
  enabled: boolean;
  notifyOnFirstRun: boolean;
}

export interface Run {
  key: string;
  id: number;
  startedAt: string;
  finishedAt: string | null;
  searches: number;
  scanned: number;
  newJobs: number;
  notified: number;
  errors: number;
}

export interface TelegramSettings {
  token: string;
  chatIds: string;
  topicId: string;
}

export interface Settings {
  feedUrl: string;
  bridgeUrl: string;
  pollMinutes: number;
  mirrorSearches: boolean;
  notificationsEnabled: boolean;
  notifyMaxPerToast: number;
  telegram: TelegramSettings;
  lastSyncAt: string;
  lastSyncError: string;
}

export interface AppMeta {
  key: string;
  value: string;
}

export interface RawJob {
  id?: string;
  title?: string;
  company?: string;
  company_id?: string;
  location?: string;
  salary?: string;
  listing_date?: string;
  listing_date_display?: string;
  posted_display?: string;
  teaser?: string;
  work_types?: string;
  work_arrangement?: string;
  classification?: string;
  subclassification?: string;
  url?: string;
  role_id?: string;
  is_featured?: boolean;
  is_verified?: boolean | null;
  is_link_out?: boolean | null;
  description_html?: string;
  description_text?: string;
  expires_at?: string;
  apply_url?: string;
  search_name?: string;
  first_seen?: string;
  last_seen?: string;
  [key: string]: unknown;
}

export interface RawSearch {
  name?: string;
  keywords?: string;
  where?: string;
  sort?: string;
  daterange?: number | null;
  worktype?: string;
  page_size?: number;
  max_pages?: number;
  max_jobs?: number;
  enrich?: boolean;
  enabled?: boolean;
  notify_on_first_run?: boolean;
  [key: string]: unknown;
}

export interface RawRun {
  id?: number;
  started_at?: string;
  finished_at?: string | null;
  searches?: number;
  scanned?: number;
  new_jobs?: number;
  notified?: number;
  errors?: number;
  [key: string]: unknown;
}

export interface FeedPayload {
  schema?: number;
  generated_at?: string;
  app?: { version?: string; stats?: Record<string, unknown> };
  searches?: RawSearch[];
  runs?: RawRun[];
  jobs?: RawJob[];
}

export const DEFAULT_SETTINGS: Settings = {
  feedUrl: "",
  bridgeUrl: "",
  pollMinutes: 5,
  mirrorSearches: false,
  notificationsEnabled: false,
  notifyMaxPerToast: 5,
  telegram: { token: "", chatIds: "", topicId: "" },
  lastSyncAt: "",
  lastSyncError: "",
};

export const DEFAULT_TRACKING: Tracking = {
  status: "inbox",
  notes: "",
  tags: [],
  seen: false,
  updatedAt: "",
};

export const SORT_OPTIONS = [
  ["newest", "Newest first"],
  ["oldest", "Oldest first"],
  ["title", "Title A–Z"],
  ["company", "Company A–Z"],
  ["salary", "Salary (high → low)"],
] as const;

export type SortKey = (typeof SORT_OPTIONS)[number][0];
