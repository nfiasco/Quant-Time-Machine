# Accessibility

Quant Time Machine aims to meet [WCAG 2.2 Level AA](https://www.w3.org/TR/WCAG22/) across the web interface and project documentation. This is a development target, not a claim of verified conformance. A comprehensive accessibility audit and assistive-technology compatibility review have not been completed.

## Standards for changes

- Use semantic headings, landmarks, links, buttons, and tables. Give controls visible labels and icon-only actions accessible names. Explain errors next to the relevant field and associate them programmatically.
- Support keyboard operation, a logical focus order, visible focus, and a skip link. Dialogs and popovers must manage and restore focus without trapping users. Focus must remain visible around sticky navigation.
- Support screen readers with meaningful names and states. Announce asynchronous status and validation changes without moving focus unnecessarily. Decorative images and animation should not create noise.
- Test light and dark themes. Target contrast of at least 4.5:1 for ordinary text, 3:1 for large text, and 3:1 for essential control boundaries and graphical information. Do not rely on color alone to convey known/future data, gains/losses, errors, or selection.
- Preserve content and controls at 200% text zoom and narrow viewports. Check reflow at 320 CSS pixels; genuinely two-dimensional tables may scroll within their own container. Pointer targets should meet WCAG's 24-by-24 CSS pixel minimum or its spacing exceptions; prefer larger touch targets where practical.
- Respect `prefers-reduced-motion`. Essential information must remain available without the landing page's scroll animation. Avoid flashing content and provide alternatives to drag-only interactions.
- Give charts and timelines a useful textual summary and accessible values. Include units, provenance, and time-zone labels; a screenshot or color legend alone is not an alternative. Add descriptive alt text and captions/transcripts when introducing informative images or media.

Implementation conventions live in [frontend/GUIDELINES.md](../frontend/GUIDELINES.md#7-accessibility). Existing building blocks include a skip link, labeled forms, semantic status text, shared focus styles, and a reduced-motion landing-page path. Reusing a component does not remove the need to check it in context.

## Checking a change

For affected UI flows, record the relevant manual checks in the PR:

1. Complete the task with Tab, Shift+Tab, Enter/Space, arrow keys where applicable, and Escape. Check focus visibility, opening/closing overlays, and error recovery.
2. Check names, headings, reading order, form errors, and status changes with a screen reader such as VoiceOver or NVDA. Record the browser and assistive technology used.
3. Check both themes, reduced motion, 200% zoom, and a narrow viewport. Verify that data states are understandable without color or animation.
4. Use browser accessibility inspection or an automated checker for additional feedback. Run the normal frontend lint, test, and build checks; passing automation alone does not establish WCAG conformance.

Prioritize barriers that prevent a core task, then serious confusion or effort, then smaller improvements. Add a regression test when it can reliably cover the repaired behavior, and repeat the affected manual steps.

## Report an accessibility barrier

Open an [accessibility issue](https://github.com/nfiasco/Quant-Time-Machine/issues/new?template=accessibility.yml). Include the page or document, what you were trying to do, the observed barrier, and your browser/device/assistive technology if relevant. Screenshots or recordings are optional; a plain-text report is sufficient. You do not need to identify a WCAG criterion or disclose a disability.

For private reports or help using the issue form, email [nfiasco@udel.edu](mailto:nfiasco@udel.edu) with the subject `Quant Time Machine accessibility`. Maintainers aim to acknowledge reports within five business days, discuss a workaround when possible, and track the fix with the reporter's consent. Do not include credentials or personal research data in a public report. Security-sensitive issues use [private vulnerability reporting](SECURITY.md).
