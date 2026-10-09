/** True when the user asked the OS/browser for less motion. */
export function prefersReducedMotion(): boolean {
  return typeof window !== "undefined" && typeof window.matchMedia === "function"
    ? window.matchMedia("(prefers-reduced-motion: reduce)").matches
    : false;
}

/** True when animated transitions can and may play: the Web Animations API
 * exists (it does not in jsdom) and reduced motion is not requested. */
export function canAnimate(): boolean {
  return (
    typeof Element !== "undefined" &&
    typeof Element.prototype.animate === "function" &&
    !prefersReducedMotion()
  );
}

/** The shared easing curve of the redesign. */
export const EASE_SPRING = "cubic-bezier(.32,.72,0,1)";

export interface Rect {
  left: number;
  top: number;
  width: number;
  height: number;
}

export function toRect(box: DOMRect): Rect {
  return { left: box.left, top: box.top, width: box.width, height: box.height };
}
