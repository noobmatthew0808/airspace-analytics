# Changelog

## v1.1.0 — 10 November 2026
- Source data remains strictly read-only from Aerodrome (no duplicate collector).
- Exclude incomplete or insufficiently sampled periods from recurring calendar averages using the existing minute-concurrency data.
- Add same-calendar-date-last-year comparison and suppress misleading percent changes when comparison coverage is insufficient.
- Enforce short read deadlines for raw database browsing and harden CSV export against spreadsheet formula injection.
- Retain standalone Python / vanilla JS architecture, mobile dashboard, presets, breakdowns, aircraft history, secure Git update button and rollback.
- Synthetic minute-coverage fixture and additional regression tests.

## v1.0.0 — 10 November 2026
- Initial read-only analytics website, installer, updater and tests.
