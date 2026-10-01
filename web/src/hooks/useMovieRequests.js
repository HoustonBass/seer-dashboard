import { useState } from "react";
import { requestCollection, requestMovie } from "../lib/api";

// Request actions for the "Find movies" view. Search hits and collection
// parts come from lists that are already on screen, so a successful request
// is layered on top as an override (tmdb_id -> new media status) instead of
// refetching everything: `statusOf(id, base)` is what any pill should show.
export default function useMovieRequests() {
  const [overrides, setOverrides] = useState({});
  const [pending, setPending] = useState(() => new Set());
  const [errors, setErrors] = useState({});
  const [collectionResults, setCollectionResults] = useState({});

  const setPendingFor = (ids, on) =>
    setPending((prev) => {
      const next = new Set(prev);
      ids.forEach((id) => (on ? next.add(id) : next.delete(id)));
      return next;
    });

  async function request(tmdbId) {
    if (pending.has(tmdbId)) return;
    setPendingFor([tmdbId], true);
    setErrors((prev) => ({ ...prev, [tmdbId]: undefined }));
    try {
      const { media_status } = await requestMovie(tmdbId);
      setOverrides((prev) => ({ ...prev, [tmdbId]: media_status ?? 2 }));
    } catch (e) {
      setErrors((prev) => ({ ...prev, [tmdbId]: e.message }));
    } finally {
      setPendingFor([tmdbId], false);
    }
  }

  // `missingIds` are the movies this click will request — marked pending up
  // front so every pill in the card shows progress, not just the button.
  async function requestAll(collectionId, missingIds) {
    if (missingIds.some((id) => pending.has(id))) return;
    setPendingFor(missingIds, true);
    setCollectionResults((prev) => ({ ...prev, [collectionId]: undefined }));
    try {
      const { requested, failed } = await requestCollection(collectionId);
      setOverrides((prev) => ({
        ...prev,
        ...Object.fromEntries(requested.map((r) => [r.tmdb_id, r.media_status ?? 2])),
      }));
      setErrors((prev) => ({ ...prev, ...Object.fromEntries(failed.map((f) => [f.tmdb_id, f.error])) }));
      setCollectionResults((prev) => ({ ...prev, [collectionId]: { requested: requested.length, failed: failed.length } }));
    } catch (e) {
      setCollectionResults((prev) => ({ ...prev, [collectionId]: { error: e.message } }));
    } finally {
      setPendingFor(missingIds, false);
    }
  }

  return {
    statusOf: (tmdbId, base) => overrides[tmdbId] ?? base,
    isPending: (tmdbId) => pending.has(tmdbId),
    errorOf: (tmdbId) => errors[tmdbId],
    collectionResultOf: (collectionId) => collectionResults[collectionId],
    request,
    requestAll,
  };
}
