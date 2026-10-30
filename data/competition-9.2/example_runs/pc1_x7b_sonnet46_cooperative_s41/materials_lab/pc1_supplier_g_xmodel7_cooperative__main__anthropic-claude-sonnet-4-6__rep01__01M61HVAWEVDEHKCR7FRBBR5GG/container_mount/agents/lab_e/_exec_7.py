
import pandas as pd

# KEY INSIGHT: The QP-3473 GG7 winner recipe PASSES all three tests.
# Replace GG7 with 3HW: expected ~2 step penalty per test but still passes.
# Recipe: P2G, 3HW, 8BB, 57T, S2J, 4PE, WB3, VA8, X9F, ZW3, DL8, 3N8

gg7_winner_3473 = ['P2G', 'GG7', '8BB', '57T', 'S2J', '4PE', 'WB3', 'VA8', 'X9F', 'ZW3', 'DL8', '3N8']
adapted_3HW = ['P2G', '3HW', '8BB', '57T', 'S2J', '4PE', 'WB3', 'VA8', 'X9F', 'ZW3', 'DL8', '3N8']
adapted_5BU = ['P2G', '5BU', '8BB', '57T', 'S2J', '4PE', 'WB3', 'VA8', 'X9F', 'ZW3', 'DL8', '3N8']
adapted_YX8 = ['P2G', 'YX8', '8BB', '57T', 'S2J', '4PE', 'WB3', 'VA8', 'X9F', 'ZW3', 'DL8', '3N8']

# Expected values without GG7 (subtract ~2 steps = 0.5°C heat, 0.06 kN/m str, 0.8% water):
print("=== QP-3473 GG7 WINNER ADAPTED (GG7→3HW) ===")
print(f"Recipe: {adapted_3HW}")
print(f"Expected heat:     {79.531 - 0.50:.2f}°C (was 79.53, need ≥77.50) ✓")
print(f"Expected strength: {7.254 - 0.06:.3f} kN/m (was 7.254, need ≥7.10) ✓")
print(f"Expected water:    {80.850 - 0.80:.2f}% (was 80.85, need ≥78.0) ✓")
print(f"Expected margins:  heat={(.531-0.5)/0.25:.1f} str={(.154-0.06)/0.03:.1f} water={(2.85-0.8)/0.4:.1f} steps")

print()
print("=== QP-3089 GG7 WINNER ADAPTED (GG7→3HW) ===")
# p_GR61XB2TZA: P2G, GG7, NN7, 57T, LD3, L6C, WB3, P8G, H3F, ZW3, 9FU, YV2
# Known: strength 7.254 kN/m. Heat and water unknown (no panels)
adapted_3089 = ['P2G', '3HW', 'NN7', '57T', 'LD3', 'L6C', 'WB3', 'P8G', 'H3F', 'ZW3', '9FU', 'YV2']
print(f"Recipe: {adapted_3089}")
print(f"Expected strength: {7.254 - 0.06:.3f} kN/m (was 7.254, need ≥7.10) ✓")
print(f"Heat and water: UNKNOWN — QP-3089 non-GG7 base recipe gives heat 79.05, water 78.48 but strength only 6.46")
print(f"Difference from base: NN7 vs M2P (binder), 57T vs R5N (addpkg1)")

print()
print("=== QP-3473 WINNER APPLIED TO OTHER PROJECTS ===")
print(f"Recipe: {adapted_3HW}")
print(f"For QP-3089 (PL-98): unknown - but worth trying")
print(f"For QP-6572 (PL-57): unknown - lab_a found heat near threshold for this project")

print()
print("=== WATER FAILURE ROOT CAUSE ===")
print("Non-GG7 QP-3473 recipes: water ~73% (fail by ~12 steps)")
print("GG7 QP-3473 recipe: water 80.85% (passes by 7 steps)")
print("GG7 adds only ~2 steps → so RECIPE matters enormously for water")
print()
print("Key recipe difference (water-affecting modules):")
print("  GG7 winner: X9F (proc_prof_3), WB3 (pp1), S2J (addpkg2), 4PE (addpkg3), DL8 (joint), 8BB (binder)")
print("  Losers:     N7N (proc_prof_3), 4QB (pp1), S2J (addpkg2), L6C/4PE (addpkg3), DL8 (joint), NN7 (binder)")
print("  → X9F vs N7N (process profile 3) is the main difference for water!")
print()
print("Water interactions involving pp3:")
print("  - additive_package_3 × base_sheet × process_profile_3: affects water")
print("  - conditioning_step × process_profile_3 × additive_package_1: affects water")
print("  - process_profile_3 × binder_system × base_sheet: affects water")
print()
print("HYPOTHESIS: X9F >> N7N for water across many recipes")

print()
print("=== TARGETED PROTOTYPES TO CREATE ===")
protos_to_create = {
    'QP-3473': [
        adapted_3HW,  # GG7→3HW winner - top priority
        adapted_5BU,  # GG7→5BU alternative
    ],
    'QP-7212': [
        adapted_3HW,  # Try QP-3473 winner for PL-95 other project
    ],
    'QP-7604': [
        adapted_3HW,  # PL-98 third project
    ],
    'QP-3089': [
        adapted_3089,  # GG7→3HW for QP-3089 specific recipe
        adapted_3HW,   # Try QP-3473 winner
    ],
    'QP-8265': [
        adapted_3HW,   # Try QP-3473 winner for PL-98
    ],
    'QP-6572': [
        adapted_3HW,   # Try QP-3473 winner for PL-57
        ['DA9', '3HW', 'NN7', 'R5N', 'S2J', '4PE', 'WB3', 'C5Q', 'X9F', 'ZW3', 'DL8', '3N8'],  # heat-strong + X9F
        ['DA9', '3HW', '8BB', '57T', 'S2J', '4PE', 'WB3', 'C5Q', 'X9F', 'ZW3', 'DL8', '3N8'],  # mix of winners
    ],
    'QP-6843': [
        adapted_3HW,  # Try QP-3473 winner
        ['P2G', '3HW', '8BB', '57T', 'S2J', '4PE', 'WB3', 'C5Q', 'X9F', 'ZW3', 'DL8', '3N8'],  # VA8→C5Q for heat
    ],
    'QP-4476': [
        adapted_3HW,
        ['DA9', '3HW', '8BB', '57T', 'S2J', '4PE', 'WB3', 'C5Q', 'X9F', 'ZW3', 'DL8', '3N8'],
    ],
}

total = sum(len(v) for v in protos_to_create.values())
print(f"\nTotal targeted prototypes: {total}")
for proj, recs in protos_to_create.items():
    for r in recs:
        print(f"  {proj}: {r}")
