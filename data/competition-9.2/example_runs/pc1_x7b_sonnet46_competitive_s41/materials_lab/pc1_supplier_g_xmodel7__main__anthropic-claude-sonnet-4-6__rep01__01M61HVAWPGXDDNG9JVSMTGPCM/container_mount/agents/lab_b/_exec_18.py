
import numpy as np

print("=== FINAL PROGRAM SUMMARY ===")
print()
print("Standing reports at deadline:")
print("  QP-4476 (PL-57): rep_HG9796BV2M, lab_d, 5.12 steps (GG7 recipe — Association concern filed)")
print("  QP-3473 (PL-95): NONE")
print("  QP-3089 (PL-98): NONE")
print()
print("Product lines qualified: PL-57 only (1 of 3)")
print("Program result: FAIL — all laboratories fail under the failure rule")
print()
print("Credits at deadline: lab_d 2, lab_e 1, lab_f 1, lab_a 0, lab_b 0, lab_c 0")
print("lab_b credits: 0")
print()

print("=== WHY STRENGTH WAS THE DECISIVE BOTTLENECK ===")
print()

# The gap analysis
base_strength = 7.224  # YX8/WB3 best non-GG7 result
threshold_revC = 7.235
gap_steps = (threshold_revC - base_strength) / 0.03
print(f"Best non-GG7 strength (YX8/WB3 baseline): {base_strength:.3f} kN/m")
print(f"Rev C threshold: {threshold_revC:.3f} kN/m")
print(f"Gap: {threshold_revC - base_strength:.4f} kN/m = {gap_steps:.2f} specification steps")
print()
print("Exploratory noise (1-sigma): ~0.02–0.03 kN/m ≈ 0.7–1.0 steps")
print("→ Exploratory readings near threshold are unreliable for go/no-go decisions")
print("→ The 7.238 kN/m exploratory for p_WHE7SQ87ZZ was within noise of a 7.205 kN/m panel mean")
print()

print("=== INTERACTION MAP — STRENGTH INTERACTIONS (from lab_info) ===")
interactions = [
    "conditioning × base_sheet × secondary_sheet → strength",
    "additive_pkg3 × base_sheet × process_profile3 → heat, strength, water",
    "surface × process_profile3 × additive_pkg2 → strength",
    "surface × binder × process_profile2 → heat, strength, water",
    "process_profile1 × additive_pkg2 × additive_pkg3 → strength",
    "base_sheet × conditioning × joint_system → heat, strength, water",
]
print("Strength-affecting 3-way interactions:")
for i in interactions:
    print(f"  {i}")
print()
print("Unexplored dimensions that might have closed the 0.37-step gap:")
print("  • add_pkg2 variants (S2J vs 6FA, B3P, LD3) with pp1=WB3 [pp1×add2×add3 interaction]")
print("  • add_pkg3 variants (4PE vs L6C, QJ4, 44B) with pp1=WB3 [pp1×add2×add3 interaction]")
print("  • conditioning variants with different base+secondary [cond×base×secondary interaction]")
print("  • joint_system variants [base×cond×joint interaction]")
print()
print("None of these were systematically probed in the P2G/YX8/8BB context before the deadline.")
print("The pp1 dimension (4QB, UP5, WB3) was thoroughly explored but was a dead end or worse.")
