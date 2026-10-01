import { describe, expect, it } from "vitest";
import { movieState, summarizeStates } from "./movieState";

describe("movieState", () => {
  it("maps Overseerr media statuses", () => {
    expect(movieState(5).key).toBe("available");
    expect(movieState(2).key).toBe("requested");
    expect(movieState(3).key).toBe("requested");
    expect(movieState(4).key).toBe("requested");
    expect(movieState(1).key).toBe("not_requested");
    expect(movieState(null).key).toBe("not_requested");
    expect(movieState(undefined).key).toBe("not_requested");
  });
});

describe("summarizeStates", () => {
  it("counts parts per state in a fixed order, skipping empty states", () => {
    const parts = [{ media_status: null }, { media_status: 5 }, { media_status: 5 }, { media_status: null }];
    expect(summarizeStates(parts)).toBe("2 available · 2 not requested");
  });
});
