import { describe, expect, it } from "vitest";
import { groupByCollection } from "./collectionGrouping";

const movie = (id, collection) => ({
  id,
  type: "movie",
  tmdb: collection ? { collection_id: collection, collection_name: `Collection ${collection}` } : {},
});

describe("groupByCollection", () => {
  it("pulls members together at the position of the first one, keeping list order", () => {
    const list = [movie(1), movie(2, 10), movie(3), movie(4, 10), movie(5, 20), movie(6, 10)];
    const entries = groupByCollection(list);

    expect(entries.map((e) => (e.kind === "group" ? `g${e.key}:${e.requests.map((r) => r.id)}` : e.request.id))).toEqual([
      1,
      "g10:2,4,6",
      3,
      5,
    ]);
  });

  it("leaves a collection with a single request as a plain row", () => {
    const entries = groupByCollection([movie(1, 10), movie(2)]);
    expect(entries.every((e) => e.kind === "row")).toBe(true);
  });

  it("never groups TV, and tolerates rows with no tmdb data", () => {
    const tv = (id) => ({ id, type: "tv", tmdb: { collection_id: 10, collection_name: "X" } });
    const entries = groupByCollection([tv(1), tv(2), { id: 3, type: "movie", tmdb: null }]);
    expect(entries.every((e) => e.kind === "row")).toBe(true);
  });

  it("carries the collection name onto the group", () => {
    const [group] = groupByCollection([movie(1, 10), movie(2, 10)]);
    expect(group.name).toBe("Collection 10");
  });
});
