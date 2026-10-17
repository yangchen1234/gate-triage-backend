# Gate Triage reference configurations

This is a **validated documentation and fixture pack for a future engine**, not an implemented scheduler, deployed product or historical reconstruction. It contains no credentials and performs no network requests. Terminal49 remains the only proposed external business-data service; source-manifest links support offline research only.

All container records, timings, resource counts, approvals, readings and job-duration distributions are synthetic. Original Ryan records are copied into `fixtures/source-record-mapping.json` with their original file hash, and remain unchanged in `data/containers.json`. No measured terminal capacity or throughput gain is claimed.

## Files

- `scenario.schema.json`: strict JSON Schema Draft 2020-12 contract for six canonical scenario files.
- `source-manifest.json`: primary-source references and bounded historical background.
- `fixtures/t49-cohort-100.json`: synthetic Terminal49-shaped collection, wrapped as `{provenance, response: {data, included}}`. This wrapper is ours, not a Terminal49 API response format.
- `fixtures/*.operator-overlay.json`: separate site measurements, jobs, synthetic resources/permission assumptions, arrival models and policy definitions.
- `fixtures/t49-backlog-100.json`: exactly 40 of 100 records have synthetic discharge dwell of at least nine days.
- `fixtures/t49-equal-service-100.json`: 100 initially eligible unfinished containers; all arrive at zero; two equivalent lanes; five-minute service. The work-conserving ceiling is 96 completions in 240 minutes.
- `scenarios/*.json`: normal operations, 2024-inspired access closure, 2017-inspired data/operations disruption, 2021-inspired backlog, weather warning without closure, equal-service negative control.

Paths inside scenarios resolve from this directory. Both cohort and overlay hashes are real SHA-256 content digests. Reference-only source links are not polled at runtime.

## Build and validate

From the repository root:

```sh
python3 docs/reference-pack/build_reference_pack.py
python3 docs/reference-pack/validate_reference_pack.py
```

Full validation requires the optional `jsonschema` package, independently of the application requirements. The validator exits with instructions if it is absent; `--structural-only` explicitly skips JSON Schema validation but retains semantic checks. The builder uses the Python standard library and writes only inside this pack. Rebuilding after the source cohort changes will intentionally change fixture hashes.

Validation checks schema, source references, path confinement, content digests, original record preservation, identities, job dependencies, resource references, time ordering, separation of site fields and provider attributes, and scenario invariants. It does **not** certify full Terminal49 API compatibility, live-account field availability, scheduler correctness, safety procedures or simulated results.

## Runtime semantics to implement

`resource.availability.capacity` is the **aggregate available capacity across `resource_ids`**, not a new capacity on every listed resource. Apply slots deterministically in listed order; for two single-lane resources, restricted capacity one means only the first is available. Future implementations may replace this with explicit per-resource calendars, retaining equivalent results.

`published_at_min` is the source's publication time, `observed_at_min` is receipt time, and `applies_at_min` is physical/effective time. Only observed information is exposed to a strategy. The 2017-inspired scenario deliberately contains distinct deliveries with the same `evidence_id`, and old business evidence arriving late. Deduplicate business evidence and prevent an older clear report from replacing a newer hold. This is **not** a claim Terminal49 suffered a historical outage.

The 2024-inspired event at minute 140 removes a simulated reported hold using the provider-native array shape. It does not remove weight, thermal, site-permission or other independent conditions. `operator` evidence never enters provider attributes. Finishing a verification job leaves it waiting for evidence, not automatically cleared.

Demand multipliers affect only future still-unobserved interarrival intervals among the fixed 100-container cohort. They do not create hidden extra containers. `gate_handoff` checks current eligibility again at start; listed prerequisites and completed verification jobs alone are insufficient. Completed journeys stay in the source cohort and metric accounting but cannot be dispatched again. Ordinary scenarios contain a mixture of simulated authorized and unauthorized movements; these flags are invented operator assumptions, never implied by the provider. Missing physical authorization remains unknown; the equal-service control explicitly supplies synthetic authorization to isolate the capacity calculation.

The 2021 additional historical port dwell fee is never activated and remains zero. Other ordinary fees, if later modeled, require separate explicit assumptions. A weather warning only creates attention; it never closes a resource without separate closure evidence.

The pack supplies inputs and invariants. Solver outputs, multi-seed comparisons and reported gains must be produced and independently checked by the future implementation.
