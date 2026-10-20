# Changelog

## 1.5.0

- Capture a selected display once and crop a label or QR codes, entirely locally.
- New QR labels tab with repeated file/screen imports, a print queue, removal and duplication.
- Full-page, quarter-page and three-across landscape layouts on A4, Letter or saved label sizes.
- Automatic pagination, decoded data captions, PDF export and printing of all pages.
- Preserve raw decoded QR bytes; block output when dense codes or captions cannot fit.
- Add synthetic regressions for QR decoding, layouts, queue operations, crop selection and multi-page printing.

## 1.4.0

- Introduced a visual template gallery with real thumbnails, search and an imported-template filter.
- Applied a subtle frosted interface with pale blue, mint and lavender accents.
- Added clearer navigation, a larger print preview and an adjacent editing panel.
- Kept print/export actions visible while the editor scrolls on smaller windows.
- Preserved local imports, saved edits, sizes and printing behaviour.

## 1.3.0

- Added a Templates tab with 15 editable designs and live previews.
- Added a private local PDF/image library with multi-page selection and removal.
- Shared paper sizes, PDF export and printing across labels and templates.
- Added saved design edits, overflow checks and an optional QR code on thank-you inserts.
- Added synthetic coverage for templates, imports, persistence, QR codes and printing.

## 1.2.1

- Updated Pillow to 12.3.0 to address known dependency vulnerabilities.
- Restricted image parsing to the advertised supported formats.

- First public release, with a clean source tree and no private test fixtures.
- Removed development-only verification commands from the packaged application.
- Added documentation, dependency licence notices and synthetic verification.

## 1.2

- Added a postage-label icon, eight label-size presets and saved custom sizes.
- Applied selected dimensions to PDF export and Windows printing.

## 1.1

- Improved label detection and orientation handling.
- Moved detection off the interface thread.
- Corrected Windows packaging to avoid incompatible ICU DLLs.
