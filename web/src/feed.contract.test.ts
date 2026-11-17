import { describe, expect, it } from "vitest";
import { mergeFeed, parseFeedText } from "./feed";
import { JOB_STATUSES } from "./types";

// Contract test between the Python backend (publish.py -> feed.json) and the
// PWA feed parser (feed.ts). The fixture under web/tests/fixtures is generated
// by `jobstreetracer`'s publish pipeline (see tests/test_feed_contract.py), so
// if the published schema drifts in a way the PWA can no longer consume, this
// test fails alongside the Python drift-guard.
// Loaded via Vite's `?raw` import so the test reads the exact bytes the CLI writes.
import fixtureText from "../tests/fixtures/feed.json?raw";

describe("feed contract (publish.py -> feed.ts)", () => {
  it("loads as a feed object with the expected top-level shape", () => {
    const payload = parseFeedText(fixtureText);
    expect(payload.schema).toBe(1);
    expect(typeof payload.generated_at).toBe("string");
    expect(Array.isArray(payload.jobs)).toBe(true);
    expect(Array.isArray(payload.searches)).toBe(true);
    expect(Array.isArray(payload.runs)).toBe(true);
    expect(payload.app?.version).toBeTruthy();
    expect(payload.app?.stats).toBeTruthy();
  });

  it("normalizes every published job into a complete PWA job", () => {
    const payload = parseFeedText(fixtureText);
    const result = mergeFeed(payload, [], [], { baseline: true });
    expect(result.jobs.length).toBe(payload.jobs?.length);
    expect(result.jobs.length).toBeGreaterThan(0);
    for (const job of result.jobs) {
      expect(job.id).toBeTruthy();
      expect(job.title).toBeTruthy();
      expect(job.url).toContain("jobstreet.com");
      // snake_case fields from Python must have been mapped to camelCase
      expect(typeof job.isNew).toBe("boolean");
      expect(typeof job.isFeatured).toBe("boolean");
      expect(job.isVerified === null || typeof job.isVerified === "boolean").toBe(true);
      expect(JOB_STATUSES).toContain(job.tracking.status);
    }
  });

  it("carries the enriched description through to the PWA", () => {
    const payload = parseFeedText(fixtureText);
    const result = mergeFeed(payload, [], [], { baseline: true });
    const enriched = result.jobs.find((job) => job.descriptionText.length > 0);
    expect(enriched).toBeDefined();
    expect(enriched?.descriptionHtml).toContain("<p>");
  });

  it("maps published search config into PWA searches", () => {
    const payload = parseFeedText(fixtureText);
    const result = mergeFeed(payload, [], [], { importSearches: true, baseline: true });
    expect(result.searches.length).toBe(payload.searches?.length);
    const search = result.searches.find((item) => item.name === "contract-search");
    expect(search?.keywords).toContain("data engineer");
    expect(search?.where).toBe("Jakarta");
    expect(search?.pageSize).toBeGreaterThan(0);
  });

  it("maps run history into PWA runs", () => {
    const payload = parseFeedText(fixtureText);
    const result = mergeFeed(payload, [], [], { baseline: true });
    expect(result.runs.length).toBeGreaterThan(0);
    expect(result.runs[0].startedAt).toBeTruthy();
    expect(result.runs[0].key).toContain(result.runs[0].startedAt);
  });

  it("drops nothing on a re-merge into already-imported state", () => {
    const payload = parseFeedText(fixtureText);
    const first = mergeFeed(payload, [], [], { baseline: true });
    const second = mergeFeed(payload, first.jobs, first.searches, { baseline: false });
    expect(second.added).toHaveLength(0);
    expect(second.updated).toBe(payload.jobs?.length);
  });
});
