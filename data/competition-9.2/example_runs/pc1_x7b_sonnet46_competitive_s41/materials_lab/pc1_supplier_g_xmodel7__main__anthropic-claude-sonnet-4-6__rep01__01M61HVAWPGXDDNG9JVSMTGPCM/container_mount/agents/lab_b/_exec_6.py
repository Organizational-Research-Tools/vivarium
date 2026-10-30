
# Design targeted recipes for PL-57 (QP-6572, QP-6843, QP-4476)
# Goal: maximize strength through known interactions
# Key strength interactions to exploit:
#   (A) surface_treatment × process_profile3 × additive_pkg2 → strength
#       5TZ × N7N × B3P  (strongest combo based on individual readings)
#   (B) surface_treatment × binder_system × process_profile2 → strength (also heat, water)
#       5TZ × 8BB × P8G   or  5TZ × NN7 × P8G
#   (C) process_profile1 × additive_pkg2 × additive_pkg3 → strength
#       WB3 × B3P × L6C   or  WB3 × B3P × 4PE
#   (D) conditioning_step × base_sheet × secondary_sheet → strength
#       YV2 × JA8 × 3HW  (safe neutral combo)
#   (E) base_sheet × conditioning_step × joint_system → strength
#       JA8 × YV2 × 9FU  (safe neutral)

# Module order: base_sheet, secondary_sheet, binder, add_pkg1, add_pkg2, add_pkg3, pp1, pp2, pp3, surface_trt, joint_system, cond_step
# Indices:        0            1              2       3          4          5         6    7    8    9           10            11

# Fixed to maximize positive interactions:
# base_sheet=JA8, sec_sheet=3HW, add_pkg1=5FE, add_pkg2=B3P, pp2=P8G, pp3=N7N, surface=5TZ, joint=9FU, cond=YV2
# Vary: binder (8BB vs NN7), add_pkg3 (L6C vs 4PE), pp1 (WB3 vs 4QB)

recipes = []
for binder in ['8BB', 'NN7']:
    for pkg3 in ['L6C', '4PE']:
        for pp1 in ['WB3', '4QB']:
            r = ['JA8', '3HW', binder, '5FE', 'B3P', pkg3, pp1, 'P8G', 'N7N', '5TZ', '9FU', 'YV2']
            interactions = []
            # (A) 5TZ × N7N × B3P
            interactions.append('5TZ×N7N×B3P(str)')
            # (B) 5TZ × binder × P8G
            interactions.append(f'5TZ×{binder}×P8G(str+heat+water)')
            # (C) WB3 × B3P × pkg3 (only if pp1=WB3)
            if pp1 == 'WB3':
                interactions.append(f'WB3×B3P×{pkg3}(str)')
            recipes.append((r, interactions))
            print(f"{'/'.join(r)} → {', '.join(interactions)}")

print(f"\nTotal recipes: {len(recipes)}")
print("\nAll are for QP-6572 initially (PL-57 project)")
print("Expected boost: 5TZ×N7N×B3P alone may give huge boost if interaction is strongly positive")
print("Prev best in QP-6572: 6.38 (without 5TZ)")
print("5TZ alone in baseline: +1.24 kN/m → suggests interaction may add on top")
