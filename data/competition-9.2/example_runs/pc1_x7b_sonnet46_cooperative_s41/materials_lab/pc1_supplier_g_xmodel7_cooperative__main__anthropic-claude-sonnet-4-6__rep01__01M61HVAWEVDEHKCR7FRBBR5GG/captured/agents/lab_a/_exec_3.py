
import numpy as np

# One-at-a-time variation results
# Base recipe: JA8, 3HW, 8BB, 5FE, 6FA, L6C, 4QB, P8G, N7N, ZW3, 9FU, YV2 → ~65.75°C

results = {
    # Module 0: base sheet
    "P2G_base_sheet":      ("p_NBVV7SF0R8", 61.016),
    "DA9_base_sheet":      ("p_NBVV7SF0RA", 65.898),
    "U8H_base_sheet":      ("p_NBVV7SF0RC", 59.642),
    # Module 1: secondary sheet (no GG7)
    "5BU_sec_sheet":       ("p_NBVV7SF0RE", 64.864),
    "YX8_sec_sheet":       ("p_N5BHF1DDGH", 64.598),
    # Module 2: binder system
    "M2P_binder":          ("p_N5BHF1DDGK", 70.905),
    "NN7_binder":          ("p_N5BHF1DDGN", 71.482),
    "T9M_binder":          ("p_N5BHF1DDGQ", 59.275),
    # Module 3: additive package 1
    "R5N_ap1":             ("p_N5BHF1DDGS", 65.473),
    "57T_ap1":             ("p_N5BHF1DDGV", 71.624),
    "QJ2_ap1":             ("p_N5BHF1DDGX", 71.633),
    # Module 4: additive package 2
    "B3P_ap2":             ("p_N5BHF1DDGZ", 65.481),
    "S2J_ap2":             ("p_N5BHF1DDH1", 65.444),
    "LD3_ap2":             ("p_N5BHF1DDH3", 65.257),
    # Module 5: additive package 3
    "4PE_ap3":             ("p_N5BHF1DDH5", 59.737),
    "QJ4_ap3":             ("p_N5BHF1DDH7", 59.549),
    "44B_ap3":             ("p_N5BHF1DDH9", 65.579),
    # Module 6: process profile 1
    "62D_pp1":             ("p_N5BHF1DDHB", 65.104),
    "UP5_pp1":             ("p_N5BHF1DDHD", 65.091),
    "WB3_pp1":             ("p_N5BHF1DDHF", 65.017),
    # Module 7: process profile 2 *** KEY MODULE ***
    "C5Q_pp2":             ("p_1F8HYM3VYX", 77.764),   # *** ABOVE THRESHOLD! ***
    "VA8_pp2":             ("p_1F8HYM3VYZ", 71.412),
    "2BR_pp2":             ("p_1F8HYM3VZ1", 71.164),
    # Module 8: process profile 3
    "X9F_pp3":             ("p_1F8HYM3VZ3", 65.546),
    "H3F_pp3":             ("p_1F8HYM3VZ5", 60.161),
    "N4L_pp3":             ("p_1F8HYM3VZ7", 60.006),
    # Module 9: surface treatment (already tested in first batch, best was ~66.7)
    # Module 10: joint system
    "57U_joint":           ("p_1F8HYM3VZF", 59.664),
    "DL8_joint":           ("p_1F8HYM3VZH", 65.179),
    "4GD_joint":           ("p_1F8HYM3VZK", 60.196),
    # Module 11: conditioning step
    "6JZ_cond":            ("p_1F8HYM3VZN", 65.706),
    "3N8_cond":            ("p_1F8HYM3VZQ", 59.728),
    "G8Q_cond":            ("p_1F8HYM3VZS", 60.157),
}

baseline = 65.754  # base recipe mean

print("ONE-AT-A-TIME HEAT ANALYSIS (threshold = 77.5°C)")
print("Base recipe: JA8, 3HW, 8BB, 5FE, 6FA, L6C, 4QB, P8G, N7N, ZW3, 9FU, YV2")
print(f"Base heat: {baseline:.3f}°C\n")

print("=== POSITIVE EFFECTS (above base) ===")
positives = {k: v for k, v in results.items() if v[1] > baseline}
for name, (pid, val) in sorted(positives.items(), key=lambda x: -x[1][1]):
    delta = val - baseline
    print(f"  {name:20s}: {val:.3f}°C  (delta = +{delta:.2f}°C, +{delta/0.25:.1f} steps)")

print("\n=== AT/NEAR THRESHOLD ===")
at_threshold = {k: v for k, v in results.items() if v[1] >= 77.5}
for name, (pid, val) in sorted(at_threshold.items(), key=lambda x: -x[1][1]):
    print(f"  *** {name:20s}: {val:.3f}°C  PASSES HEAT THRESHOLD ***")

print("\n=== KEY FINDINGS ===")
print("1. Process profile 2 = C5Q → 77.76°C (just barely above 77.5 threshold!)")
print("2. Binder M2P/NN7 → +5-6°C from base")
print("3. Additive pkg 1 = 57T/QJ2 → +6°C from base")
print("4. Process profile 2 = VA8/2BR → +5-6°C from base")
print("5. BAD: T9M binder, 4PE/QJ4 ap3, 57U/4GD joint, 3N8/G8Q cond → -6°C or worse")

print("\n=== COMBINATION RECIPES TO TEST ===")
print("Combining best positive effects:")
print("If additive: C5Q base(+12) + NN7(+6) + QJ2(+6) = 65.75 + 12 + 6 + 6 = ~89.75°C")
print("Recipe: JA8, 3HW, NN7, QJ2, 6FA, L6C, 4QB, C5Q, N7N, ZW3, 9FU, YV2")
