import {useEffect, useState} from "react";

const TOUCH_QUERY = "(hover: none) and (pointer: coarse)";

/** Mobile = stacked PDF|Data tabs. Landscape phones stay mobile even when width > 800px. */
export function computeViewportLayout() {
  const width = window.innerWidth;
  const height = window.innerHeight;
  const touch = typeof matchMedia !== "undefined" && matchMedia(TOUCH_QUERY).matches;
  const landscape = width > height;
  const narrow = width <= 800;
  const short = height <= 520;

  const isMobile = narrow || (touch && short && width <= 1200);

  return {isMobile, landscape, touch};
}

export function useViewportLayout() {
  const [layout, setLayout] = useState(computeViewportLayout);

  useEffect(() => {
    const update = () => setLayout(computeViewportLayout());
    update();
    const touchMql = matchMedia(TOUCH_QUERY);
    touchMql.addEventListener("change", update);
    addEventListener("resize", update);
    addEventListener("orientationchange", update);
    return () => {
      touchMql.removeEventListener("change", update);
      removeEventListener("resize", update);
      removeEventListener("orientationchange", update);
    };
  }, []);

  return layout;
}
