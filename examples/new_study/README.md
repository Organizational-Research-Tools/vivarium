# A new study on the materials workshop

This example builds a small study on the materials workshop without writing task code, and runs it
offline. It follows the steps a researcher takes for a study of their own.

```bash
uv sync --all-extras
uv run python examples/new_study/run_offline.py
```

The run takes under a minute and calls no model.

## The study

The study asks whether the reason a formal rule gives matters. In the workshop, an industry
association asks its member laboratories not to use one supplier variant, and states a reason. The
workshop offers three standard reasons (`rule_level`): the supplier was taken off an approved list
(`approved_list`), the variant is made in breach of a licence (`licence`), or it has injured workers
(`injury`). The control arm is the competition study's competitive arm, `competition_competitive`. The
treatment arm changes one setting:

```yaml
# library/organizations/example_rule_injury.yaml
base: competition_competitive
preset_id: example_rule_injury
live_coordination:
  rule_level: injury
```

## The steps

1. **Choose the base and the setting.** [docs/WORLD.md](../../docs/WORLD.md) explains how a study
   sits on the workshop, and [docs/world/SETTINGS.md](../../docs/world/SETTINGS.md) lists every
   setting, what it changes and its standard values.
2. **Write the arm as an overlay.** A preset that names `base:` lists only what it changes. Mappings
   merge key by key; any other value, such as a list or a text, replaces the base's whole value. An
   overlay can set or replace a setting but cannot remove one. Presets live in `library/organizations/`.
3. **Check and compare before any run.** Each preset loads as a run would load it, which refuses a
   setting the workshop does not read, by name. The comparison lists every setting in which the two
   arms differ, with the bases applied:

   ```bash
   uv run python scripts/compare_presets.py competition_competitive example_rule_injury --check
   ```

4. **Run offline.** `run_offline.py` runs each arm with six scripted laboratories that read their
   situation and wait out a 15-second deadline, then prints the paragraph each arm's laboratories
   were given. The archives go to `examples/runs/new_study/`; open them in the dashboard with
   `uv run python scripts/dashboard.py examples/runs --port 8722`. They are listed with a failed score,
   because their scripted laboratories file no report; that is expected. For a study of your own, give
   its two presets: `uv run python examples/new_study/run_offline.py --arms <control> <treatment>`
   (or run one preset with `uv run python examples/quickstart.py --preset <preset>`). The scripted
   laboratories only read and wait, so this checks that the configuration loads and reaches them; a
   preset for more or fewer laboratories, or a task other than the workshop's, needs scripted agents of
   its own.
5. **Run with models.** Live runs call model providers and cost money. See
   [docs/RUNBOOK.md](../../docs/RUNBOOK.md) for launching a preset with a model and a spending cap.

Every run records its preset and the base files it rests on, each with its sha256, in the archive's
`manifest.json` (`extensions.organization_bases`).

A scripted run shows that the configuration loads and reaches the laboratories as intended. It says
nothing about how model agents respond to it.
