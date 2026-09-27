import { useState } from "react";

// A counter that changes value to signal "something happened, refetch" to a
// child component via a `refreshKey` prop (see DvdActivityBadge/
// FailedQuickAddsButton) — the value itself is meaningless, only that it
// changed. Extracted since App.jsx needed this exact pattern twice.
export default function useRefreshSignal() {
  const [key, setKey] = useState(0);
  function bump() {
    setKey((k) => k + 1);
  }
  return [key, bump];
}
