// Overseerr status enums, confirmed against the live instance — see
// scripts/discovery/seerr.md. Kept here rather than inline so display logic
// doesn't leak into every component that shows a status.

export const REQUEST_STATUS = {
  1: "Pending",
  2: "Approved",
  3: "Declined",
};

export const MEDIA_STATUS = {
  1: "Unknown",
  2: "Pending",
  3: "Processing",
  4: "Partially Available",
  5: "Available",
};

export function mediaStatusLabel(status) {
  return MEDIA_STATUS[status] ?? `Unknown (${status})`;
}

export function requestStatusLabel(status) {
  return REQUEST_STATUS[status] ?? `Unknown (${status})`;
}
