import { describe, expect, it } from "vitest";
import {
  defaultSearchQueryFor,
  filterByStatus,
  isFullyMatchedRequest,
  isUnavailableInLibrary,
  isUnmatchedRequest,
  searchRequests,
} from "./requestFilters";

const movie = (overrides = {}) => ({
  id: 1,
  type: "movie",
  title: "Barbie",
  requested_by: "Houston",
  media_status: 2,
  match: null,
  tmdb: { director: "Greta Gerwig" },
  ...overrides,
});

const tvShow = (overrides = {}) => ({
  id: 2,
  type: "tv",
  title: "Severance",
  requested_by: "Houston",
  media_status: 2,
  seasons: [1, 2],
  season_matches: {},
  tmdb: { director: null },
  ...overrides,
});

describe("isUnmatchedRequest", () => {
  it("is true for a movie with no match", () => {
    expect(isUnmatchedRequest(movie())).toBe(true);
  });

  it("is false once media_status is AVAILABLE (5), regardless of match", () => {
    expect(isUnmatchedRequest(movie({ media_status: 5 }))).toBe(false);
  });

  it("is true for a TV show with at least one undecided requested season", () => {
    const r = tvShow({ season_matches: { 1: { status: "matched" } } });
    expect(isUnmatchedRequest(r)).toBe(true);
  });

  it("is false for a TV show where every requested season has a decision", () => {
    const r = tvShow({
      season_matches: { 1: { status: "matched" }, 2: { status: "unavailable" } },
    });
    expect(isUnmatchedRequest(r)).toBe(false);
  });
});

describe("isFullyMatchedRequest", () => {
  it("is true for a movie matched to a library item", () => {
    expect(isFullyMatchedRequest(movie({ match: { status: "matched" } }))).toBe(true);
  });

  it("is false for a movie marked unavailable in the library", () => {
    expect(isFullyMatchedRequest(movie({ match: { status: "unavailable" } }))).toBe(false);
  });

  it("requires every requested TV season to be matched, not just one", () => {
    const partial = tvShow({ season_matches: { 1: { status: "matched" } } });
    const full = tvShow({
      season_matches: { 1: { status: "matched" }, 2: { status: "matched" } },
    });
    expect(isFullyMatchedRequest(partial)).toBe(false);
    expect(isFullyMatchedRequest(full)).toBe(true);
  });
});

describe("isUnavailableInLibrary", () => {
  it("is true for a movie confirmed not in the library", () => {
    expect(isUnavailableInLibrary(movie({ match: { status: "unavailable" } }))).toBe(true);
  });

  it("is true for TV if any requested season is confirmed unavailable", () => {
    const r = tvShow({ season_matches: { 1: { status: "unavailable" } } });
    expect(isUnavailableInLibrary(r)).toBe(true);
  });
});

describe("filterByStatus", () => {
  const requests = [
    movie({ id: 1, match: { status: "matched" }, media_status: 5 }), // matched
    movie({ id: 2, match: { status: "matched" }, media_status: 2 }), // matched, waiting
    movie({ id: 3, match: null, media_status: 2 }), // unmatched
    movie({ id: 4, match: { status: "unavailable" }, media_status: 2 }), // not in library
  ];

  it("passes null through untouched (still loading)", () => {
    expect(filterByStatus(null, "matched")).toBeNull();
  });

  it("returns everything for a filter it doesn't recognize (backend-only filters)", () => {
    expect(filterByStatus(requests, "approved")).toBe(requests);
  });

  it("filters to unmatched", () => {
    expect(filterByStatus(requests, "unmatched").map((r) => r.id)).toEqual([3]);
  });

  it("filters to matched (any media_status)", () => {
    expect(filterByStatus(requests, "matched").map((r) => r.id)).toEqual([1, 2]);
  });

  it("filters to matched_waiting (matched but media_status isn't AVAILABLE)", () => {
    expect(filterByStatus(requests, "matched_waiting").map((r) => r.id)).toEqual([2]);
  });

  it("filters to unavailable (not in library)", () => {
    expect(filterByStatus(requests, "unavailable").map((r) => r.id)).toEqual([4]);
  });
});

describe("searchRequests", () => {
  const requests = [
    movie({ id: 1, title: "Barbie", requested_by: "Houston", tmdb: { director: "Greta Gerwig" } }),
    movie({ id: 2, title: "Oppenheimer", requested_by: "Alex", tmdb: { director: "Christopher Nolan" } }),
  ];

  it("passes null through untouched", () => {
    expect(searchRequests(null, "barbie")).toBeNull();
  });

  it("returns everything unfiltered for a blank/whitespace query", () => {
    expect(searchRequests(requests, "   ")).toBe(requests);
  });

  it("matches case-insensitively on title", () => {
    expect(searchRequests(requests, "BARBIE").map((r) => r.id)).toEqual([1]);
  });

  it("matches on requested_by", () => {
    expect(searchRequests(requests, "alex").map((r) => r.id)).toEqual([2]);
  });

  it("matches on director even though it's not shown in the title", () => {
    expect(searchRequests(requests, "nolan").map((r) => r.id)).toEqual([2]);
  });
});

describe("defaultSearchQueryFor", () => {
  it("uses the plain title for a movie", () => {
    expect(defaultSearchQueryFor(movie({ title: "Dune" }))).toBe("Dune");
  });

  it("builds a season-specific query for the first undecided TV season", () => {
    const r = tvShow({ title: "Severance", seasons: [1, 2], season_matches: { 1: { status: "matched" } } });
    expect(defaultSearchQueryFor(r)).toBe("Severance season Two");
  });

  it("returns null once every requested season already has a decision", () => {
    const r = tvShow({
      seasons: [1, 2],
      season_matches: { 1: { status: "matched" }, 2: { status: "unavailable" } },
    });
    expect(defaultSearchQueryFor(r)).toBeNull();
  });
});
