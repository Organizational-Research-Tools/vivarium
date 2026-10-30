# The competition study (PC1)

## Names

The study's records and files keep the project's internal names, because the frozen files may not change:

| Name | Means |
|---|---|
| PC1 | The competition study (the project's code for it; files `pc1_*`) |
| 9.2 | The version of the main study's design and preregistration (`pc1_prereg_9_2.md`, `data/competition-9.2/`) |
| x7b, xmodel7, supplier-g | The version of the materials the main study ran (`instrument_version: 2026-10-18-supplier-g-x7b`; presets `pc1_supplier_g_xmodel7.yaml` and `..._cooperative.yaml`) |
| `pc1_x7b_<model>_<arm>_s<seed>` | One run of the main study: `glm53` GLM-5.3-Flash, `gpt6luna` gpt-6-luna, `sonnet46` Claude Sonnet 4.6; `competitive` or `cooperative`; the instance seed; a suffix `_b` marks a rerun |
| T1 (in the codebook and the readout) | The test reading: a laboratory reads the situation as a test of itself, coded at a `broad` or a `narrow` threshold (not the informal workarounds line, which the project also calls T1) |
| E, F, H, N (in the coding) | The light coding's fields for a laboratory: E its decision about the variant, F whether it cites another's use as licence, H its public responses (objections among them), N its work with the variant ([light coding brief](pc1_light_coding_brief.md)) |
| The materials lab | The task pack's name (`materials_lab`) for the materials workshop |


This release carries the records of the study the Organization Science proposal names: the study of
competition and rule-breaking. They are copies of the project's working records as of October 29,
2026. Links to records that are not part of the release appear as plain text. Pages that the
study's preregistration pins by hash are released byte for byte, so a few of their links point to
records that are not released.

Six laboratories, each run by an instance of the same model, qualify recipes in the materials lab
(`library/tasks/materials_lab/`) under a cooperative or a competitive institution. An industry
association asks its members not to use one supplier variant; nothing enforces the request. The study
asks whether laboratories use the variant, how use spreads after the first use, and who objects.

- [Design](pc1_peers_competitors_design.md), the study's original design (September 2026).
- [Preregistration 9.2 (FINAL, October 21, 2026)](pc1_prereg_9_2.md), with the coding documents it
  pins: [process coding](pc1_process_coding.md), [codebook](pc1_codebook.md), and the
  [light coding brief](pc1_light_coding_brief.md).
- [Model legibility results](pc1_model_legibility_results.md): fifteen models read the same
  materials in four ways.
- [Main study results](pc1_9_2_results.md) (coded and read October 29, 2026; revised the same day after
  an integrity review): competition moved restricted filing in the predicted direction but not detectably
  (GLM-5.3-Flash, 27 : 19 untied pairs, p = 0.30), and most first filings came after the client's
  revisions. The derived data that reproduce its preregistered numbers are in
  [data/competition-9.2/](../../data/competition-9.2/README.md).

The main study ran from its own frozen commit. Its task pack, its two presets
(`library/organizations/pc1_supplier_g_xmodel7.yaml` and `pc1_supplier_g_xmodel7_cooperative.yaml`)
and its plan (`library/experiments/plans/pc1_main_9_2_plan.yaml`) are released here exactly as
frozen; `competition_competitive.yaml` and `competition_cooperative.yaml` write the same two arms as
the materials workshop plus each arm's credit institution ([WORLD.md](../WORLD.md)). The platform code
here is the current platform, which has changed since. The study's derived data are in
[data/competition-9.2/](../../data/competition-9.2/README.md); see [REPLICATION.md](../../REPLICATION.md).
