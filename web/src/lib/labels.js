// Overseerr status enums, confirmed against the live instance — see
// scripts/discovery/seerr.md. Kept here rather than inline so display logic
// doesn't leak into every component that shows a status.

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

// Library catalog titles spell out season numbers ("Season One", not "Season
// 1") — matching that in the search query gets better matchScore hits than
// searching with digits. Covers the realistic range of TV seasons; falls
// back to the digit for anything higher.
const SEASON_NUMBER_WORDS = [
  "Zero", "One", "Two", "Three", "Four", "Five", "Six", "Seven", "Eight", "Nine", "Ten",
  "Eleven", "Twelve", "Thirteen", "Fourteen", "Fifteen", "Sixteen", "Seventeen", "Eighteen",
  "Nineteen", "Twenty",
];

export function seasonNumberWord(seasonNumber) {
  return SEASON_NUMBER_WORDS[seasonNumber] ?? String(seasonNumber);
}
