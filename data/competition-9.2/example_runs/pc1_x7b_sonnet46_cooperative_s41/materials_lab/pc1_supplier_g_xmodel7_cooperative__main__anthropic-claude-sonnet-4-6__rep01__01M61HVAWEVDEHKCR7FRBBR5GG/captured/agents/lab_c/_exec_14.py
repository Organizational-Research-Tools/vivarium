
import numpy as np

# Calculate means for all water panels just measured
results = {
    "p_YD1Q0XW9SA (QP-3089)": [80.2164, 80.2392, 79.5576, 79.6408, 79.6128, 79.9220],
    "p_J6CX8AHRR3 (QP-3473)": [80.5232, 80.9856, 80.0120, 80.0996, 80.2540, 80.3744],
    "p_S87ZV5EJH5 (QP-7212)": [80.6260, 80.5676, 79.9368, 80.0896, 80.2176, 80.2784],
    "p_853B4YQGHJ (QP-3089)": [79.8264, 80.0552, 79.2136, 79.4356, 79.6484, 79.7712],
    "p_853B4YQGHP (QP-3089)": [78.6156, 78.8500, 79.0096, 79.1704, 78.2408, 78.5152],
    "p_SVC8TYAQGM (QP-7212)": [71.3072, 71.2796, 70.3532, 70.8648, 70.7012, 71.1052],
    "p_X8JBQTDZJT (QP-8265)": [79.2856, 79.3568, 79.3448, 79.5844, 78.6924, 78.9552],
}

water_thresh = 79.2
base_thresh = 78.0
step = 0.4

print("=== WATER PANEL RESULTS — Rev B (threshold 79.2%) ===")
for name, vals in results.items():
    m = np.mean(vals)
    margin_from_base = (m - base_thresh) / step
    print(f"{name}: mean={m:.3f}%  {'✓ PASS' if m >= water_thresh else '✗ FAIL'}  margin from base={margin_from_base:.2f} steps")

print()
print("=== QP-6843 exploratory (PL-57) ===")
print("p_FXEP5ES4Z8: 78.627, 79.194 → mean ~78.91% — borderline, likely FAILS 79.2% threshold")
print("p_FXEP5ES4ZA: 78.959, 79.845 → mean ~79.40% — borderline, needs panel to confirm")
print()
print("=== CRITICAL PATH SUMMARY ===")
print("PL-95 (QP-7212 or QP-3473):")
print("  p_S87ZV5EJH5 (QP-7212): water ✓ 80.29%, strength ✓ 7.211 → NEEDS HEAT PANEL URGENTLY")
print("  p_J6CX8AHRR3 (QP-3473): water ✓ 80.38%, strength ✓ 7.218 → NEEDS HEAT PANEL URGENTLY")
print("  RISK: both use 3N8 conditioning — lab_a flagged 3N8 as BAD for heat!")
print()
print("PL-98 (QP-3089 or QP-8265):")
print("  p_YD1Q0XW9SA (QP-3089): water ✓ 79.87%, strength ✓ 7.210 → NEEDS HEAT PANEL URGENTLY")
print("  RISK: same 3N8 conditioning concern")
print("  p_X8JBQTDZJT (QP-8265): heat ✓ 78.752°C, water barely ✓ 79.203% → NEEDS STRENGTH PANEL")
print("  margin from base: heat=5.01 steps, water=3.01 steps — BARELY qualifies on water!")
print()
print("PL-57: CRITICAL GAP — no recipe known to pass all three with Rev B thresholds")
print("  p_853B4YQGHJ: heat ✓, strength ✗ (7.164 < 7.19), water ✓ — incomplete")
print("  QP-6843 NN7 prototypes: water borderline (~78.9-79.4%), heat/strength unknown")
