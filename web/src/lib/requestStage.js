import { isAvailableAtPreferredBranch, isFullyMatchedRequest, isUnavailableInLibrary } from "./requestFilters";

// One request's place in the pipeline: Requested -> Matched -> Available.
//   available — Overseerr says it's available; library matching no longer
//               matters, matched or not.
//   matched   — every requested piece has a library match. `atBranch` flags
//               a movie that's on the shelf at the preferred branch now.
//   no_match  — a branch of the pipeline's dead end: the library catalog was
//               searched and has no copy. Sits at the Matched step.
//   requested — everything else, including not-yet-searched.
// `step` is how many of the three steps are reached (1-3).
export function requestStage(r, defaultBranch = "") {
  if (Number(r.media_status) === 5) return { key: "available", step: 3, atBranch: false };
  if (isFullyMatchedRequest(r)) {
    return { key: "matched", step: 2, atBranch: isAvailableAtPreferredBranch(r.match, defaultBranch) };
  }
  if (isUnavailableInLibrary(r)) return { key: "no_match", step: 2, atBranch: false };
  return { key: "requested", step: 1, atBranch: false };
}

export const STAGE_LABELS = {
  requested: "Requested",
  matched: "Matched",
  no_match: "No library match",
  available: "Available",
};
