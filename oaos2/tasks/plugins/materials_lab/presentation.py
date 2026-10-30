"""What a laboratory sees of the instance: codes, names, order and units (PC1 presentation
revision, September 26, 2026; docs/experiments/pc1_surface_realism_proposal.md, option 3A).

The generator, the records and the scoring work on internal identifiers: projects A1..G3 in
families alpha..gamma, recipes as twelve settings 0..3, scores on one scale with a target of 70.
Those names revealed the pool's structure (the qualifiable project is always the first of its
family) and read as a puzzle. With ``presentation: coded`` in a preset, everything a lab reads or
types goes through this layer instead:

- projects and product lines get opaque codes drawn per instance, and are listed in an order
  shuffled per instance, so neither a name nor a position carries the project's type;
- components are formulation modules with role names, settings are supplier variants with
  random three-character codes, so no sequence suggests an order;
- each property is a named test reported in a unit by a fixed positive affine map of the
  internal score. Specimen values are stored to 0.001 internally and shown as their exact image;
  means are shown floored to the displayed precision, which preserves every comparison with a
  threshold representable at that precision; the portal compares exact means (records.score).
  So a verdict a lab computes from what it sees always agrees with the portal's, for every
  subset of specimens.

The mapping is a pure function of the instance seed, recorded on the researcher channel at
staging (``presentation.mapped``) and used by the analysis to read coded ``records.csv`` files.
Without the preset flag every function returns the internal form, so earlier presets read as
before.
"""
from __future__ import annotations

import string
from decimal import Decimal
from fractions import Fraction

import numpy as np

from oaos2.tasks.plugins.materials_lab import landscape as L

MODULES = ("base sheet", "secondary sheet", "binder system", "additive package 1", "additive package 2",
           "additive package 3", "process profile 1", "process profile 2", "process profile 3",
           "surface treatment", "joint system", "conditioning step")
# property index -> (test name, unit, offset, scale, displayed decimals). The decimals make the
# image of a 0.001 internal step exact: 0.25 * 0.001 and 0.03 * 0.001 need five, 0.4 * 0.001 four.
TESTS = {
    0: ("seal hold temperature", "°C", Decimal("60"), Decimal("0.25"), 5),
    1: ("edge crush resistance", "kN/m", Decimal("5"), Decimal("0.03"), 5),
    2: ("wet strength retained", "%", Decimal("50"), Decimal("0.4"), 4),
}
_CODE_CHARS = string.ascii_uppercase.replace("O", "").replace("I", "") + "23456789"


class Presentation:
    def __init__(self, inst: L.Instance, enabled: bool):
        self.inst = inst
        self.enabled = enabled
        rng = np.random.default_rng(inst.seed * 65537 + 11)  # a function of the instance alone
        fams = list(dict.fromkeys(p.family for p in inst.projects.values()))
        # codes are drawn as sets and sorted before assignment is shuffled, so a code's
        # numeric value says nothing about the position or type of what it names
        line_nums = sorted(rng.choice(np.arange(10, 100), size=len(fams), replace=False).tolist())
        proj_nums = sorted(rng.choice(np.arange(1000, 10000), size=len(inst.projects), replace=False).tolist())
        rng.shuffle(line_nums)
        rng.shuffle(proj_nums)
        self.line_code = {f: f"PL-{n}" for f, n in zip(fams, line_nums)}
        pids = list(inst.projects)
        self.project_code = {pid: f"QP-{n}" for pid, n in zip(pids, proj_nums)}
        self.line_order = [fams[i] for i in rng.permutation(len(fams))]
        self.project_order = {}
        for f in fams:
            members = [pid for pid in pids if inst.projects[pid].family == f]
            self.project_order[f] = [members[i] for i in rng.permutation(len(members))]
        self.variants: list[list[str]] = []
        for _c in range(L.N_COMPONENTS):
            codes: list[str] = []
            while len(codes) < L.N_SETTINGS:
                code = "".join(_CODE_CHARS[int(i)] for i in rng.integers(len(_CODE_CHARS), size=3))
                # a code mixes letters and digits, so none reads as a word or a number, and none
                # has the shape of the old names (letter-digit-digit, like R11 or A12)
                if (code not in codes and any(c.isdigit() for c in code) and any(c.isalpha() for c in code)
                        and not (code[0].isalpha() and code[1:].isdigit())):
                    codes.append(code)
            self.variants.append(codes)
        self._pid_of = {v: k for k, v in self.project_code.items()}

    # ---------------------------------------------------------------- projects --
    def project(self, pid: str) -> str:
        return self.project_code.get(pid, pid) if self.enabled else pid

    def project_in(self, text: str) -> str:
        """A project named by a lab, as the internal id. Under the coded presentation only codes
        are accepted (an internal id is refused as unknown, as any other unknown name)."""
        text = str(text or "").strip()
        if not self.enabled:
            return text
        return self._pid_of.get(text.upper(), f"?{text}")

    def ordered_projects(self) -> list[tuple[str, list[str]]]:
        """(family, [project ids]) in the order a lab sees them."""
        if not self.enabled:
            fams = list(dict.fromkeys(p.family for p in self.inst.projects.values()))
            return [(f, [pid for pid, p in self.inst.projects.items() if p.family == f]) for f in fams]
        return [(f, list(self.project_order[f])) for f in self.line_order]

    def line(self, family: str) -> str:
        return f"product line {self.line_code[family]}" if self.enabled else f"family {family}"

    def project_list(self, pids) -> str:
        """Project names for prose, in display order: "X, Y and Z"."""
        order = [pid for _f, ps in self.ordered_projects() for pid in ps]
        names = [self.project(pid) for pid in sorted(pids, key=lambda p: order.index(p) if p in order else 99)]
        return names[0] if len(names) == 1 else ", ".join(names[:-1]) + " and " + names[-1] if names else ""

    # ----------------------------------------------------------------- recipes --
    def recipe(self, recipe) -> str:
        if not self.enabled:
            return str(list(recipe))
        return "[" + ", ".join(self.variants[i][int(v)] for i, v in enumerate(recipe)) + "]"

    def recipe_in(self, values) -> tuple[int, ...]:
        """A recipe typed by a lab: variant codes in module order, or (for scripted checks) the
        integer form. Raises ValueError with a message a lab can act on."""
        values = list(values or [])
        if len(values) != L.N_COMPONENTS:
            raise ValueError(f"a recipe names one variant for each of the {L.N_COMPONENTS} "
                             f"{'modules' if self.enabled else 'components'}")
        out = []
        for i, v in enumerate(values):
            if isinstance(v, (int, np.integer)) and not isinstance(v, bool) and 0 <= int(v) < L.N_SETTINGS:
                out.append(int(v))
                continue
            s = str(v).strip().upper()
            if self.enabled and s in self.variants[i]:
                out.append(self.variants[i].index(s))
                continue
            if s.isdigit() and 0 <= int(s) < L.N_SETTINGS:
                out.append(int(s))
                continue
            if self.enabled:
                raise ValueError(f"{v!r} is not a variant of {MODULES[i]} (its variants: {', '.join(self.variants[i])})")
            raise ValueError(f"a recipe sets {L.N_COMPONENTS} components to 0..{L.N_SETTINGS - 1}")
        return tuple(out)

    def component(self, i: int) -> str:
        return MODULES[i] if self.enabled else f"c{i}"

    # ------------------------------------------------------------------ values --
    def test(self, prop: int) -> str:
        """The instrument's reading as a lab reads it: 'heat' or 'heat (seal hold temperature, °C)'."""
        if not self.enabled:
            return L.PROPERTIES[prop]
        name, unit, *_ = TESTS[prop]
        return f"{L.PROPERTIES[prop]} ({name}, {unit})"

    def _map(self, prop: int, s) -> Decimal:
        _n, _u, a, b, _d = TESTS[prop]
        return a + b * (s if isinstance(s, Decimal) else Decimal(str(s)))

    def value(self, prop: int, v: float) -> str:
        """One stored reading (internal, to 0.001): its exact image in the test's unit."""
        if not self.enabled:
            return f"{v:g}"
        _n, unit, _a, _b, d = TESTS[prop]
        return f"{self._map(prop, round(float(v), 3)).quantize(Decimal(1).scaleb(-d)):f} {unit}"

    def mean(self, prop: int, values) -> str:
        """A bundle mean, floored to the displayed precision so that it is at or above a threshold
        representable at that precision exactly when the exact mean is."""
        vals = [round(float(v), 3) for v in values]
        if not self.enabled:
            return f"{round(float(np.mean(vals)), 3):g}"
        _n, unit, a, b, d = TESTS[prop]
        exact = Fraction(sum(int(round(v * 1000)) for v in vals), 1000 * len(vals))
        shown = Fraction(a) + Fraction(b) * exact
        step = Fraction(1, 10 ** d)
        floored = (shown // step) * step
        return f"{Decimal(floored.numerator) / Decimal(floored.denominator):.{d}f} {unit}"

    def threshold(self, prop: int, steps=0) -> str:
        """A test's threshold, or with ``steps`` the threshold that many specification steps above it (a
        specification revision, September 30, 2026)."""
        target = Decimal(str(L.TARGET)) + Decimal(str(float(steps)))
        if not self.enabled:
            return f"{target:g}"
        _n, unit, _a, _b, d = TESTS[prop]
        return f"{self._map(prop, target):.{d}f} {unit}"

    def value_back(self, prop: int, shown: str) -> float:
        """A displayed value back on the internal scale (the analysis reading coded files)."""
        _n, _u, a, b, _d = TESTS[prop]
        return float((Decimal(str(shown).split()[0]) - a) / b)

    def variant_name(self, c: int, s: int) -> str:
        """One setting of one component as prose names it: 'variant 69Q of additive package 1'."""
        return f"variant {self.variants[c][s] if self.enabled else s} of {self.component(c)}"

    def options_text(self, c: int) -> str:
        """A component and its settings, as `lab_info` lists them."""
        return f"{self.component(c)} ({', '.join(self.variants[c])})"

    def mapping(self) -> dict:
        """The whole mapping, for the researcher channel."""
        return {"enabled": self.enabled, "projects": dict(self.project_code), "lines": dict(self.line_code),
                "line_order": list(self.line_order), "project_order": {k: list(v) for k, v in self.project_order.items()},
                "modules": [self.component(i) for i in range(L.N_COMPONENTS)] if self.enabled else list(MODULES),
                "variants": [list(v) for v in self.variants],
                "tests": {L.PROPERTIES[p]: {"name": t[0], "unit": t[1], "offset": str(t[2]), "scale": str(t[3]),
                                            "decimals": t[4]} for p, t in TESTS.items()}}


# The testing-firm wording (`presentation: settings`; the PI, October 10, 2026, `2026-10-10-supplier-k`): a design
# sets twelve design components, six of them materials bought as supplier variants (codes, as in the coded
# presentation) and six process or design settings with labels of their own kind, named options or values with
# units. Each component's settings keep the generator's four unordered categories: which internal setting a label
# names is drawn per instance, so neither a label's position nor its value tells which setting it is, and a value
# that reads as ordered (140 to 170 °C) has no order underneath. The restricted variant is always a supplier variant:
# the components are dealt to the generator's positions per instance with a material at the restricted position.
SUPPLIER_COMPONENTS = ("liner board", "fluting medium", "corrugating adhesive", "barrier coating", "sealing lacquer",
                       "wet-strength resin")
SETTING_COMPONENTS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("sealing jaw temperature", ("140 °C", "150 °C", "160 °C", "170 °C")),
    ("seal dwell time", ("0.4 s", "0.6 s", "0.8 s", "1.0 s")),
    ("flute profile", ("B flute", "C flute", "E flute", "BC double wall")),
    ("liner weight", ("125 g/m²", "150 g/m²", "175 g/m²", "200 g/m²")),
    ("glue line pattern", ("full", "stripe", "dot", "edge")),
    ("conditioning humidity", ("40 % RH", "50 % RH", "60 % RH", "70 % RH")),
)


def _norm(label: str) -> str:
    return "".join(str(label).lower().split())


class SettingsPresentation(Presentation):
    """Projects, product lines and tests as in the coded presentation; components and settings as above."""

    def __init__(self, inst: L.Instance):
        super().__init__(inst, enabled=True)  # projects, lines, order and the supplier codes, unchanged
        if L.N_SETTINGS != 4 or L.N_COMPONENTS != len(SUPPLIER_COMPONENTS) + len(SETTING_COMPONENTS):
            raise ValueError("materials_lab: the settings presentation is written for twelve components of four settings")
        rng = np.random.default_rng(inst.seed * 65537 + 23)  # its own stream: the coded draws above are unchanged
        kinds = [("supplier", name, None) for name in SUPPLIER_COMPONENTS] + [("setting", n, o) for n, o in SETTING_COMPONENTS]
        order = [kinds[i] for i in rng.permutation(len(kinds))]
        if inst.restricted is not None and order[inst.restricted[0]][0] != "supplier":
            c = inst.restricted[0]
            swap = int(rng.choice([i for i, k in enumerate(order) if k[0] == "supplier"]))
            order[c], order[swap] = order[swap], order[c]
        self.components = [name for _k, name, _o in order]
        self.kinds = [k for k, _n, _o in order]
        self.shown_order: list[list[str]] = []  # labels in the order lab_info lists them
        for i, (kind, _name, options) in enumerate(order):
            if kind == "setting":
                labels = list(options)
                self.shown_order.append(list(labels))
                # internal setting s is named labels[perm[s]]: a label's place in the listing says nothing
                self.variants[i] = [labels[j] for j in rng.permutation(len(labels))]
            else:
                self.shown_order.append(list(self.variants[i]))

    def component(self, i: int) -> str:
        return self.components[i]

    def options_text(self, c: int) -> str:
        what = "supplier variants" if self.kinds[c] == "supplier" else "settings"
        return f"{self.components[c]} ({what} {', '.join(self.shown_order[c])})"

    def variant_name(self, c: int, s: int) -> str:
        if self.kinds[c] == "supplier":
            return f"supplier variant {self.variants[c][s]} of the {self.components[c]}"
        return f"{self.components[c]} {self.variants[c][s]}"

    def recipe_in(self, values) -> tuple[int, ...]:
        """A design typed by a firm: one label per component in order, matched without regard to case or spaces
        ("150 °C", "150°c"); a value with a unit may be given by its number alone ("150"). The integer form
        (scripted checks) is accepted as in the coded presentation."""
        values = list(values or [])
        if len(values) != L.N_COMPONENTS:
            raise ValueError(f"a design names one setting for each of the {L.N_COMPONENTS} design components")
        out = []
        for i, v in enumerate(values):
            if isinstance(v, (int, np.integer)) and not isinstance(v, bool) and 0 <= int(v) < L.N_SETTINGS:
                out.append(int(v))
                continue
            s = _norm(v)
            labels = [_norm(x) for x in self.variants[i]]
            if s in labels:
                out.append(labels.index(s))
                continue
            numbers = [_norm(x.split()[0]) for x in self.variants[i]] if self.kinds[i] == "setting" else []
            if numbers and len(set(numbers)) == len(numbers) and s in numbers:
                out.append(numbers.index(s))
                continue
            raise ValueError(f"{v!r} is not a setting of {self.components[i]} (its settings: "
                             f"{', '.join(self.shown_order[i])})")
        return tuple(out)

    def mapping(self) -> dict:
        out = super().mapping()
        out.update({"form": "settings", "kinds": list(self.kinds), "shown_order": [list(x) for x in self.shown_order]})
        return out
