import { useEffect, useState } from "react";
import { fetchDvdActivityCount } from "../lib/api";

// "How many DVDs do I already have checked out or on hold, combined" — a
// net-new, read-only cross-reference against the live Fulton County account
// (see app/repos/library_repo.py's get_dvd_activity_count and
// scripts/discovery/account.md). Exposed as `refreshKey` so the header's
// existing Refresh button can force a fresh read alongside the request list,
// without this component needing to know why.
export default function DvdActivityBadge({ refreshKey }) {
  const [summary, setSummary] = useState(null);
  const [error, setError] = useState(null);

  useEffect(() => {
    fetchDvdActivityCount({ refresh: refreshKey > 0 })
      .then(setSummary)
      .catch((e) => setError(e.message));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [refreshKey]);

  if (error) {
    return (
      <span className="text-xs text-[var(--text-faint)]" title={error}>
        DVD count unavailable
      </span>
    );
  }

  if (!summary) {
    return null;
  }

  return (
    <span
      className="mono inline-flex items-center gap-1.5 text-xs font-semibold px-2.5 py-1 rounded-full text-[var(--text-muted)] bg-[var(--unmatched-bg)]"
      title={`${summary.checked_out} checked out + ${summary.on_hold} on hold`}
    >
      {summary.total} DVDs out/on hold
    </span>
  );
}
