import { useEffect, useState } from "react";

// Genuine structural differences (not just reflow — e.g. the match panel
// rendering inline under the selected row vs. a separate sticky side panel,
// see App.jsx) need a JS-level branch, not pure CSS. Matches the same
// breakpoint as the 2-pane grid switch (md, 768px) by construction, so the
// two can't drift into two independently-tuned numbers.
const DESKTOP_QUERY = "(min-width: 768px)";

export default function useIsMobile() {
  const [isMobile, setIsMobile] = useState(() => !window.matchMedia(DESKTOP_QUERY).matches);

  useEffect(() => {
    const mql = window.matchMedia(DESKTOP_QUERY);
    function onChange(e) {
      setIsMobile(!e.matches);
    }
    mql.addEventListener("change", onChange);
    return () => mql.removeEventListener("change", onChange);
  }, []);

  return isMobile;
}
