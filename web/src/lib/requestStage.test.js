import { describe, expect, it } from "vitest";
import { requestStage } from "./requestStage";

const movie = (overrides = {}) => ({ id: 1, type: "movie", media_status: 2, match: null, ...overrides });

describe("requestStage", () => {
  it("is requested when nothing has been matched yet", () => {
    expect(requestStage(movie())).toEqual({ key: "requested", step: 1, atBranch: false });
  });

  it("is matched once the library match is chosen", () => {
    expect(requestStage(movie({ match: { status: "matched" } }))).toMatchObject({ key: "matched", step: 2 });
  });

  it("flags pickup at the preferred branch only when a copy is available there", () => {
    const match = { status: "matched", branches: [{ branch_code: "MILTON", branch_name: "Milton", status: "AVAILABLE" }] };
    expect(requestStage(movie({ match }), "milton").atBranch).toBe(true);
    expect(requestStage(movie({ match }), "alpharetta").atBranch).toBe(false);
    expect(requestStage(movie({ match }), "").atBranch).toBe(false);
  });

  it("reports no library match as a dead end at the matched step", () => {
    expect(requestStage(movie({ match: { status: "unavailable" } }))).toMatchObject({ key: "no_match", step: 2 });
  });

  it("is available whenever Overseerr says so, matched or not", () => {
    expect(requestStage(movie({ media_status: 5 }))).toMatchObject({ key: "available", step: 3 });
    expect(requestStage(movie({ media_status: 5, match: { status: "matched" } }))).toMatchObject({ key: "available" });
    expect(requestStage(movie({ media_status: 5, match: { status: "unavailable" } }))).toMatchObject({ key: "available" });
  });

  it("treats a TV show as matched only when every requested season is", () => {
    const tv = (season_matches) => ({ id: 2, type: "tv", media_status: 2, seasons: [1, 2], season_matches });
    expect(requestStage(tv({ 1: { status: "matched" } })).key).toBe("requested");
    expect(requestStage(tv({ 1: { status: "matched" }, 2: { status: "matched" } })).key).toBe("matched");
    expect(requestStage(tv({ 1: { status: "matched" }, 2: { status: "unavailable" } })).key).toBe("no_match");
  });
});
