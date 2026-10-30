
import numpy as np

# Compute means for the new PL-57 heat panels
results = {
    'p_8JN5B4DPHJ (JA8/3HW/8BB/H3F)': [56.51450, 56.56375, 56.63400, 56.13475, 56.25325, 56.33875],
    'p_8JN5B4DPHM (DA9/3HW/8BB/H3F)': [67.95025, 68.11200, 68.30050, 67.60100, 67.66225, 67.93450],
    'p_PHXDGYDJZ4 (lab_b QP-4476)':   [67.21675, 67.40025, 67.52775, 67.62050, 67.10875, 67.09400],
    'p_DS954NKK8W (lab_c QP-6843)':    [68.30950, 68.55675, 68.55650, 68.52325, 68.11775, 68.20125],
    'p_AJDCM7NSKX (lab_e QP-6843)':   [67.98125, 68.10725, 68.15150, 68.37450, 67.78300, 67.89350],
}

threshold_4476 = 78.25
threshold_6843 = 68.25  # approximate for QP-6843 (PL-57 projects share similar thresholds?)

print("=== HEAT PANEL RESULTS ===")
print(f"Revision B heat threshold: ≥78.25°C (QP-4476)")
print()

for name, vals in results.items():
    mean = np.mean(vals)
    steps_from_thresh = (mean - threshold_4476) / 0.25
    print(f"{name}")
    print(f"  Mean: {mean:.4f}°C | Steps from 78.25: {steps_from_thresh:+.1f} | {'PASS' if mean >= threshold_4476 else 'FAIL'}")
    print()

print("=== KEY INSIGHT ===")
print("JA8/YX8/M2P → heat 78.19°C (−0.24 steps)")
print("DA9/3HW/M2P → heat 78.37°C (+0.48 steps)")  
print("P2G/3HW/8BB → heat 74.24°C (−16 steps)")
print("DA9/3HW/8BB → heat 67.93°C (−41 steps)  ← CATASTROPHIC: 8BB kills heat!")
print("JA8/3HW/8BB → heat 56.41°C (−87 steps)  ← CATASTROPHIC: 8BB kills heat!")
print()
print("CONCLUSION: 8BB binder is INCOMPATIBLE with good heat on PL-57.")
print("Only M2P binder gives heat near threshold on PL-57.")
print()
print("The only non-GG7 path: secondary sheet that preserves M2P's heat advantage")
print("while improving strength over the JA8/YX8/M2P recipe (strength=6.554 kN/m).")
print()
print("NEW CANDIDATE: JA8/3HW/M2P = GG7 recipe with GG7→3HW")
print("- Heat: 3HW×7KL×M2P interaction vs GG7×7KL×M2P — unknown direction")
print("- Strength: cond×base×secondary = 3N8×JA8×3HW vs 3N8×JA8×YX8 — might be better!")
print("- Water: secondary NOT in water interactions → should stay ~80.70%")
