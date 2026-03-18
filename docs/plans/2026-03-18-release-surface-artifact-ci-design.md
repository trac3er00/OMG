# Release Surface Artifact CI Fix Design

## Problem

`release-readiness` fails in CI with `release_surface_drift: dist/public/release-surface.json not found`.

The final readiness gate validates `output_root/dist/public/release-surface.json`, but the compile jobs only upload `artifacts/release`. Today `compile_release_surfaces()` writes its manifest under repo-root `dist/`, so the assembled artifact tree never carries the release-surface manifest that the final gate expects.

## Options

### Recommended: Emit release-surface manifests into `output_root/dist/<channel>/`

Keep the readiness gate strict and make contract compilation stage the release-surface manifest inside the compiled artifact tree. This keeps CI validation self-contained and aligned with the uploaded artifacts.

### Alternative: Fall back to repo-root `dist/` during readiness checks

This would make the gate pass when the checkout happens to contain the manifest, but it hides the artifact packaging gap and weakens the guarantee that the assembled release bundle is complete.

## Design

Add a focused contract-compiler regression test that asserts `compile_contract_outputs(..., output_root=tmp_path, channel="public")` writes `tmp_path/dist/public/release-surface.json`. Then patch the compile path to emit the release-surface manifest into `output_root/dist/<channel>/` using the canonical release-surface registry data, without mutating repo-root docs or release notes.

## Verification

- Contract compiler regression for emitted release-surface manifest
- Release readiness drift tests
- Workflow structure tests to ensure the existing artifact flow expectations still hold
