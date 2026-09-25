import { useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";

// A small inline thumbnail that shows a much larger preview next to itself
// on hover. Rendered via a portal straight into <body> (not a CSS
// transform/absolute child) specifically because both call sites — search
// result rows and the match panel itself — sit inside a scrolling container
// (`overflow-y-auto` for the sticky right panel), which clips anything that
// tries to grow past its own bounds. A portal escapes that entirely.
export default function HoverZoomImage({ src, zoomSrc, alt = "", className = "", zoomWidth = 260, onError }) {
  const [rect, setRect] = useState(null);
  const [loaded, setLoaded] = useState(false);
  const boxRef = useRef(null);

  // Swapping `src` on an existing <img> leaves the previous image's decoded
  // pixels on screen until the new one finishes loading — jarring when
  // switching between requests/search results, since the old poster/jacket
  // just sits there looking current. Reset per `src` so the skeleton below
  // covers that gap instead of a stale image.
  useEffect(() => {
    setLoaded(false);
  }, [src]);

  function handleEnter() {
    setRect(boxRef.current.getBoundingClientRect());
  }

  const zoomHeight = zoomWidth * 1.45; // rough DVD/poster aspect ratio, just for clamping
  const showOnRight = rect ? rect.right + zoomWidth + 16 < window.innerWidth : true;
  const left = rect ? (showOnRight ? rect.right + 10 : rect.left - zoomWidth - 10) : 0;
  const top = rect ? Math.min(Math.max(rect.top, 8), window.innerHeight - zoomHeight - 8) : 0;

  return (
    <>
      <span
        ref={boxRef}
        onMouseEnter={handleEnter}
        onMouseLeave={() => setRect(null)}
        className={`relative overflow-hidden block ${className}`}
      >
        <img
          src={src}
          alt={alt}
          className="absolute inset-0 w-full h-full object-cover"
          onLoad={() => setLoaded(true)}
          onError={(e) => {
            setLoaded(true);
            onError?.(e);
          }}
        />
        {!loaded && <span className="absolute inset-0 animate-pulse bg-[var(--rule)]" />}
      </span>
      {rect &&
        createPortal(
          <img
            src={zoomSrc || src}
            alt={alt}
            style={{ position: "fixed", top, left, width: zoomWidth, zIndex: 1000 }}
            className="rounded-md shadow-2xl border border-[var(--rule-strong)] pointer-events-none bg-[var(--surface)]"
          />,
          document.body,
        )}
    </>
  );
}
