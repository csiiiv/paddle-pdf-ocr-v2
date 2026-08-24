/** Copy for per-pane help dialogs (PDF vs Data). */

export function PdfPaneHelpContent({isMobile = false}) {
  return <>
    <p>Official NEP PDF with optional row highlights linked to the data table.</p>
    <ul>
      <li><strong>Click a highlighted row</strong> on the page to select the matching tree entry (when sync is on).</li>
      <li><strong>Page</strong> — type a page number or use the arrows; left/right arrow keys work too.</li>
      <li><strong>Zoom</strong> — Fit W, Fit H, or a custom percent.</li>
      <li><strong>Row boxes</strong> — Show overlays, Hide them but keep clicks, or turn Off.</li>
      <li><strong>Sync</strong> — When on, PDF and data selections stay linked; when off, the tree still selects locally but PDF clicks are ignored.</li>
    </ul>
    {isMobile &&
      <>
        <h3>On mobile</h3>
        <ul>
          <li>Use the floating page buttons (prev / page / next) for quick navigation.</li>
          <li>Tap the page chip to open zoom, row boxes, and sync controls.</li>
          <li>Pinch to zoom; one finger scrolls when zoomed in.</li>
          <li>Selecting a PDF row switches to Data and focuses the matching tree entry.</li>
        </ul>
      </>}
    {!isMobile &&
      <ul>
        <li>Drag the center splitter to resize the PDF and data panes.</li>
      </ul>}
  </>;
}

export function DataPaneHelpContent({isMobile = false}) {
  return <>
    <p>Extracted budget hierarchy with amounts — By Operating Unit and PAP tables.</p>
    <ul>
      <li><strong>Click a row</strong> to select it and jump the PDF to that page (toast if no PDF location).</li>
      <li><strong>Tabs</strong> — switch between By Operating Unit and PAP.</li>
      <li><strong>Hierarchy level</strong> (By OU) — PREXC code vs PDF layout; row order stays the same, only indents change.</li>
      <li><strong>Search</strong> — filters label, code, and kind; matching rows reveal their ancestors.</li>
      <li><strong>Page filter</strong> — show only rows on the current PDF page.</li>
      <li><strong>Expand / Collapse</strong> — chevrons on rows with children, or use the toolbar buttons.</li>
      <li><strong>Column widths</strong> — drag the grip button between column headers to resize.</li>
    </ul>
    {isMobile &&
      <>
        <h3>On mobile</h3>
        <ul>
          <li>Use the <strong>PDF | Data</strong> switch at the top to change panes.</li>
          <li>Tap the menu button to switch By OU / PAP tabs.</li>
          <li>Selecting a tree row with a PDF location switches to the PDF pane.</li>
        </ul>
      </>}
  </>;
}
