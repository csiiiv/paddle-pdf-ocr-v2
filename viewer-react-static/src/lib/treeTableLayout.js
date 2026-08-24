/** Reserved header gutter (px) for the column-resize control beside labels. */
export const COL_GRIP_GUTTER = {desktop: 30, compact: 36};

export function colGripGutter(compact = false) {
  return compact ? COL_GRIP_GUTTER.compact : COL_GRIP_GUTTER.desktop;
}

/** Column width including the header resize gutter. */
export function colWidth(contentWidth, compact = false) {
  return contentWidth + colGripGutter(compact);
}
