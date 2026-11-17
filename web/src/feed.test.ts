import { describe, expect, it } from "vitest";
import {
  mergeFeed,
  normalizeSearch,
  parseFeedText,
  parseSalary,
  searchesToToml,
} from "./feed";
import { DEFAULT_TRACKING, type Job, type Search } from "./types";

function job(id: string, overrides: Partial<Job> = {}): Job {
  return {
    id,
    title: `Job ${id}`,
    company: "Acme",
    companyId: "",
    location: "Jakarta",
    salary: "",
    listingDate: "",
    listingDateDisplay: "1d ago",
    postedDisplay: "",
    teaser: "",
    workTypes: "Full time",
    workArrangement: "",
    classification: "",
    subclassification: "",
    url: `https://id.jobstreet.com/id/job/${id}`,
    roleId: "",
    isFeatured: false,
    isVerified: null,
    isLinkOut: null,
    descriptionHtml: "",
    descriptionText: "",
    expiresAt: "",
    applyUrl: "",
    searchName: "test",
    firstSeen: "2026-11-01T00:00:00Z",
    lastSeen: "2026-11-01T00:00:00Z",
    isNew: false,
    tracking: { ...DEFAULT_TRACKING, tags: [] },
    ...overrides,
  };
}

const search: Search = {
  name: "test",
  keywords: "data engineer",
  where: "Jakarta",
  sort: "Relevance",
  daterange: 14,
  worktype: "",
  pageSize: 30,
  maxPages: 3,
  maxJobs: 0,
  enrich: true,
  enabled: true,
  notifyOnFirstRun: false,
};

describe("feed parsing and merging", () => {
  it("parses feed objects and JSONL", () => {
    const feed = parseFeedText(JSON.stringify({ jobs: [{ id: "1", title: "A" }], searches: [] }));
    expect(feed.jobs?.[0].id).toBe("1");
    const jsonl = parseFeedText('{"id":"1","title":"A"}\n{"id":"2","title":"B"}\n');
    expect(jsonl.jobs).toHaveLength(2);
  });

  it("does not flag the first import as new", () => {
    const result = mergeFeed({ jobs: [{ id: "1" }, { id: "2" }] }, [], []);
    expect(result.jobs).toHaveLength(2);
    expect(result.added.every((item) => item.isNew === false)).toBe(true);
  });

  it("honours an explicit baseline even when local jobs exist", () => {
    const result = mergeFeed({ jobs: [{ id: "2" }] }, [job("1")], [search], { baseline: true });
    expect(result.added[0].isNew).toBe(false);
    const later = mergeFeed({ jobs: [{ id: "3" }] }, result.jobs, [search], { baseline: false });
    expect(later.added[0].isNew).toBe(true);
  });

  it("flags subsequent unseen jobs and preserves tracking", () => {
    const existing = job("1", {
      tracking: { ...DEFAULT_TRACKING, status: "applied", notes: "keep me", tags: ["remote"] },
    });
    const result = mergeFeed(
      { jobs: [{ id: "1", title: "Updated" }, { id: "2", title: "New" }] },
      [existing],
      [search],
    );
    expect(result.added.map((item) => item.id)).toEqual(["2"]);
    expect(result.added[0].isNew).toBe(true);
    const kept = result.jobs.find((item) => item.id === "1");
    expect(kept?.title).toBe("Updated");
    expect(kept?.tracking.status).toBe("applied");
    expect(kept?.tracking.notes).toBe("keep me");
  });

  it("keeps local jobs missing from the feed", () => {
    const result = mergeFeed({ jobs: [{ id: "2" }] }, [job("1"), job("2")], [search]);
    expect(result.jobs.map((item) => item.id).sort()).toEqual(["1", "2"]);
  });

  it("imports searches only when asked or when empty", () => {
    const withSearches = mergeFeed({ jobs: [], searches: [{ name: "x", keywords: "x" }] }, [job("1")], [search]);
    expect(withSearches.searches.map((item) => item.name)).toEqual(["test"]);
    const forced = mergeFeed(
      { jobs: [], searches: [{ name: "x", keywords: "x" }] },
      [job("1")],
      [search],
      { importSearches: true },
    );
    expect(forced.searches.map((item) => item.name)).toEqual(["x"]);
    expect(forced.importedSearches).toBe(1);
  });
});

describe("exports", () => {
  it("writes valid-looking TOML search blocks", () => {
    const toml = searchesToToml([search]);
    expect(toml).toContain("[[search]]");
    expect(toml).toContain('keywords = "data engineer"');
    expect(toml).toContain("daterange = 14");
    expect(toml).toContain("enabled = true");
  });

  it("normalizes config fields from either naming style", () => {
    const normalized = normalizeSearch({ name: "x", keywords: "k", page_size: 50, maxPages: 2 });
    expect(normalized.pageSize).toBe(50);
    expect(normalized.maxPages).toBe(2);
  });

  it("parses common salary formats", () => {
    expect(parseSalary("Rp 10.000.000 per month")).toBe(10_000_000);
    expect(parseSalary("Rp 8.000.000 – Rp 12.000.000")).toBe(12_000_000);
    expect(parseSalary("Negotiable")).toBe(0);
  });
});
