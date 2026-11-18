# dVRK Community Publications — Agent Guidelines

## Publication Inclusion Criteria (Strict Guardrail)

Only add or retain a publication in the repository if the work was **made possible by the existence of the dVRK**, routed into two mutually exclusive bibliographies:

### Tier 1: `publications.bib` (Core dVRK Research & Dataset Creators)
1. **dVRK / dVRK-Si Hardware**: Develops, modifies, integrates sensors/tools with, or experimentally evaluates on physical dVRK or dVRK-Si manipulators/consoles.
2. **dVRK Software & Simulators**: Develops or evaluates algorithms using dVRK software stacks (`sawIntuitiveResearchKit`, cisst/SAW) or dVRK simulation environments (e.g., AMBF, SurRoL, dVRL, Orbit-Surgical, dVRK CoppeliaSim/Unity virtual platforms).
3. **Dataset Creators (`dvrk_dataset`)**: Introduces/releases a public dVRK-acquired dataset. Set `dvrk_dataset = {<Readable Dataset Name>}` **if and only if** the entry documents the creation of a dataset.
4. **Hybrid dVRK + Dataset Works**: Papers that use **both** physical dVRK/dVRK simulators and a shared dVRK dataset belong in `publications.bib` (without `dvrk_dataset`, unless creating a new dataset).
5. **dVRK-Focused Reviews (`RE`)**: Reviews specifically centered on the dVRK platform, its dynamics/software, or the dVRK research community (e.g., D'Ettorre et al. 2021, Zhang et al. 2026).

### Tier 2: `dataset_publications.bib` (Dataset-Only Downstream Research)
- Papers that **only** train or benchmark on dVRK-acquired datasets (e.g., SurgRIPE, SurgPose, ROSMA, Open-H, CRCD, LUMICS, MV-dVRK) without using dVRK hardware, dVRK software, or dVRK simulators belong in `dataset_publications.bib`.
- **Distinct schema**: `dataset_publications.bib` uses `datasets = {<CreatorBibID1> and <CreatorBibID2>}` referencing entries with `dvrk_dataset` in `publications.bib`, plus `peer_reviewed` and `date_added` (it does **not** use `research_field`, `data_type`, `dvrk_site`, `dvrk_cites`, or `dvrk_dataset`).
- **Mutual exclusivity**: No paper (citation key or DOI) may appear in both `publications.bib` and `dataset_publications.bib`.

### Explicit Exclusions (Record in `rejected_papers.json`)
- **Author-only overlap**: Do **not** include papers merely because one or more authors belong to a dVRK site or have previously published on the dVRK.
- **General clinical or robotics reviews**: Reject broad specialty or technology surveys (e.g., general colorectal surgery, acute care surgery, general haptic/RL surveys) that only cite dVRK papers as literature examples.
- **Related-work-only mentions & non-dVRK platforms**: Reject papers that mention `dVRK` or `SurRoL` only in Introduction/Related Work while running experiments exclusively on other robots (e.g., UR5, KUKA LBR, Franka, Raven, clinical-only da Vinci recordings without dVRK) or non-dVRK simulators.
- **Mandatory experimental verification**: Never add a candidate based solely on full-text keyword hits or citations. If the abstract does not explicitly confirm dVRK hardware, simulator, or dataset usage, inspect the Methods/Experiments section of the full text first.

## Bibliography & Validation Conventions
- **Python environment**: Run maintenance scripts with `./.venv/bin/python` from the repository root.
- **BibTeX hygiene**:
  - Format `author` as `Last, First and Last, First` (direct UTF-8 diacritics, braced mixed-case acronyms in `title` such as `{dVRK}` or `{6DoF}`).
  - Keep `abstract` plain UTF-8 prose free of raw LaTeX math (`$...$`), `\pm`, or HTML entities/tags.
  - Use only tag codes defined in `custom_tags.json` (`research_field`, `data_type`, `peer_reviewed`, `dvrk_site`), joined by ` and `.
- **Required post-edit check**: After modifying `publications.bib`, run:
  - `./.venv/bin/python scripts/update_bib.py` (or `--offline` when only removing/formatting entries)
  - `./.venv/bin/python scripts/update_bib.py --check --strict-format` (must pass with `0` errors and `0` advisories).

