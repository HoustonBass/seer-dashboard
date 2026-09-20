import { useRef, useState } from "react";
import { createPortal } from "react-dom";

// A small inline thumbnail that shows a much larger preview next to itself
// on hover. Rendered via a portal straight into <body> (not a CSS
// transform/absolute child) specifically because both call sites — search
// result rows and the match panel itself — sit inside a scrolling container
// (`overflow-y-auto` for the sticky right panel), which clips anything that
// tries to grow past its own bounds. A portal escapes that entirely.
export default function HoverZoomImage({ src, zoomSrc, alt = "", className = "", zoomWidth = 260, onError }) {
  const [rect, setRect] = useState(null);
  const imgRef = useRef(null);

  function handleEnter() {
    setRect(imgRef.current.getBoundingClientRect());
  }

  const zoomHeight = zoomWidth * 1.45; // rough DVD/poster aspect ratio, just for clamping
  const showOnRight = rect ? rect.right + zoomWidth + 16 < window.innerWidth : true;
  const left = rect ? (showOnRight ? rect.right + 10 : rect.left - zoomWidth - 10) : 0;
  const top = rect ? Math.min(Math.max(rect.top, 8), window.innerHeight - zoomHeight - 8) : 0;

  return (
    <>
      <img
        ref={imgRef}
        src={src}
        alt={alt}
        className={className}
        onMouseEnter={handleEnter}
        onMouseLeave={() => setRect(null)}
        onError={onError}
      />
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
