"""Package inspectable design sources and fixtures, never secrets/runtime data."""
import hashlib
import json
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

ROOT = Path(__file__).resolve().parents[1]
FILES = [
    "docs/START_HERE.zh-CN.md", "docs/gate-triage-technical-specification.zh-CN.md",
    "docs/gate-triage-technical-specification.zh-CN.html", "docs/realtime-decision-contract.zh-CN.md",
    "docs/demo-runbook.zh-CN.md", "docs/workbench-verification.md", "docs/spec-tools-requirements.txt",
    "scripts/render_technical_spec.py", "scripts/package_development_brief.py",
    "README-workbench.md", "data/containers.json",
    "docs/spatial-emergency-and-scale.zh-CN.md", "docs/mature-solution-comparison.zh-CN.md",
    "docs/simulation-evaluation.zh-CN.md", "docs/engineering-audit.md", "docs/emergency-workflow.md",
    "docs/relational-scale.md", "docs/scale-evaluation.zh-CN.md",
    "scripts/benchmark_workbench.py", "scripts/benchmark_scale.py", "scripts/audit_benchmark_results.py", "scripts/inspect_scale_database.py",
]


def main():
    paths = [ROOT / p for p in FILES]
    paths += [p for p in (ROOT / "docs/reference-pack").rglob("*") if p.is_file() and "__pycache__" not in p.parts]
    paths += list((ROOT / "docs/screenshots").glob("*.png"))
    for evaluation in ("workbench-2026-10-17", "scale-2026-10-17"):
        paths += [p for p in (ROOT / "evaluation" / evaluation).rglob("*") if p.is_file() and "__pycache__" not in p.parts]
    paths = sorted(set(paths))
    manifest = {"artifact": "Gate Triage development specification", "version": "1.2",
                "created_date": "2026-10-17", "scope": "Design contracts and synthetic fixtures. Runnable implementation source is in the repository's independent branch.",
                "files": [{"path": str(p.relative_to(ROOT)), "sha256": hashlib.sha256(p.read_bytes()).hexdigest(), "bytes": p.stat().st_size} for p in paths]}
    manifest_path = ROOT / "docs/development-brief-manifest.json"
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n")
    with ZipFile(ROOT / "docs/gate-triage-development-brief.zip", "w", ZIP_DEFLATED) as archive:
        for p in paths + [manifest_path]:
            archive.write(p, p.relative_to(ROOT))
    print(f"Packaged {len(paths)} source files and checksum manifest")


if __name__ == "__main__":
    main()
