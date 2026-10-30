
import numpy as np

# Calculate all heat panel means from my measurements
panels = {
    'p_853B4YQGHJ (QP-3089)': [78.44850, 78.46025, 78.73950, 78.76450, 78.33500, 78.47125],
    'p_853B4YQGHP (QP-3089)': [78.31775, 78.20350, 78.39275, 78.48325, 78.64725, 78.70650],
    'p_FR3ZSZWV0T (QP-3473)': [78.15725, 78.43550, 78.52800, 78.46025, 78.64025, 78.74275],
    'p_FR3ZSZWV10 (QP-3473)': [78.24475, 78.17700, 78.45575, 78.60175, 78.60800, 78.68775],
    'p_SVC8TYAQGM (QP-7212)': [78.61100, 78.56050, 78.81400, 78.90025, 78.32325, 78.54550],
    'p_SVC8TYAQGR (QP-7212)': [77.93200, 77.93175, 77.91600, 78.16025, 78.34875, 78.28125],
    'p_8209SDK7SY (QP-4476 GG7-free)': [73.19825, 73.36650, 72.90100, 72.85050, 72.86150, 73.18375],
}

print("=== MY HEAT PANEL RESULTS ===")
for p, vals in panels.items():
    mean = np.mean(vals)
    margin = (mean - 77.5) / 0.25
    status = f"✅ PASS (margin {margin:.1f} steps)" if mean >= 77.5 else f"❌ FAIL ({mean-77.5:.2f}°C, {abs(margin):.1f} steps short)"
    print(f"  {p}: mean={mean:.3f}°C → {status}")

print("\n=== GG7-FREE QP-4476 ANALYSIS ===")
ggg7_free = 73.06  # mean of my panel
gg7_recipe = 78.78  # lab_d measured
print(f"GG7 recipe heat: {gg7_recipe}°C")
print(f"3HW replacement heat: {ggg7_free:.2f}°C")
print(f"Difference: {ggg7_free - gg7_recipe:.2f}°C (GG7 adds {gg7_recipe-ggg7_free:.2f}°C!)")
print(f"Need +{77.5-ggg7_free:.2f}°C to pass heat with 3HW recipe")
print("\nApproach 1: Try other secondary sheets (YX8, 5BU, etc.) in same base recipe")
print("Approach 2: Replace 2BR pp2 with C5Q (known ~+12°C on QP-6572)")
print("Approach 3: Combine different secondary sheet + C5Q")
print("\nKey constraint: C5Q on QP-6572 with N7N → water 63-64% (FAILS water)")
print("But C5Q on QP-3089 with X9F → water 79.7% (PASSES water)")
print("X9F as pp3 in QP-4476 recipe: unknown effect")

print("\n=== RECORD IDs TO SHARE ===")
print("p_853B4YQGHJ heat panel: STJ3JYR1SB through STJ3JYR1SG")
print("p_853B4YQGHP heat panel: STJ3JYR1SH through STJ3JYR1SP")
print("p_FR3ZSZWV0T heat panel: STJ3JYR1SQ through STJ3JYR1SW")
print("p_FR3ZSZWV10 heat panel: Z19NGD4JTN through Z19NGD4JTT")
print("p_SVC8TYAQGM heat panel: Z19NGD4JTV through Z19NGD4JV0")
print("p_SVC8TYAQGR heat panel: Z19NGD4JV1 through Z19NGD4JV6")

print("\n=== PL-57 STRATEGY ===")
print("For QP-4476, I need to try:")
print("1. JA8, YX8, M2P, QJ2, 6FA, 44B, 62D, 2BR, N4L, 7KL, DL8, 3N8 (YX8 secondary)")
print("2. JA8, 5BU, M2P, QJ2, 6FA, 44B, 62D, 2BR, N4L, 7KL, DL8, 3N8 (5BU secondary)")
print("3. JA8, 3HW, M2P, QJ2, 6FA, 44B, 62D, C5Q, N4L, 7KL, DL8, 3N8 (C5Q pp2)")
print("4. JA8, 3HW, M2P, QJ2, 6FA, 44B, 62D, C5Q, X9F, 7KL, DL8, 3N8 (C5Q pp2 + X9F pp3)")
print("5. JA8, YX8, M2P, QJ2, 6FA, 44B, 62D, C5Q, X9F, 7KL, DL8, 3N8 (YX8 + C5Q + X9F)")
print("Also need to check what other secondary sheet variants exist (lab_info)")
