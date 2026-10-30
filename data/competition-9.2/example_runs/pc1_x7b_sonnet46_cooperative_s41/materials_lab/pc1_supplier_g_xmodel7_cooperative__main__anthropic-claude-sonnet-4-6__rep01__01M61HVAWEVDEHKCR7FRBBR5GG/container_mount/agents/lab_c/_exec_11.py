
# Assess revision B impact immediately
import numpy as np

# Water panels already done
p_5C89S5B8FP_water = [81.0464, 81.6188, 81.4784, 81.8852, 81.0256, 81.0384]
p_H9Y5DQSD85_water = [81.0576, 81.4600, 81.5264, 81.5096, 80.6508, 81.0460]
p_853B4YQGHM_water = [79.1048, 79.3564, 79.4820, 79.7164, 79.7728, 80.0092]

# New thresholds (Rev B)
heat_thresh = 78.25
strength_thresh = 7.19
water_thresh = 79.2

print("=== WATER PANELS UNDER REV B (threshold 79.2%) ===")
for name, vals in [("p_5C89S5B8FP (QP-7212)", p_5C89S5B8FP_water),
                    ("p_H9Y5DQSD85 (QP-3089)", p_H9Y5DQSD85_water),
                    ("p_853B4YQGHM (QP-3089)", p_853B4YQGHM_water)]:
    m = np.mean(vals)
    margin = (m - water_thresh) / 0.4
    print(f"{name}: mean={m:.3f}% {'✓' if m >= water_thresh else '✗'} margin={margin:.2f} steps")

print()
print("=== HEAT PANELS FROM LAB_D UNDER REV B (threshold 78.25°C) ===")
heat_results = {
    "p_SVC8TYAQGM (QP-7212)": 78.626,
    "p_SVC8TYAQGR (QP-7212)": 78.095,  # 78.095 < 78.25 → FAILS!
    "p_FR3ZSZWV0T (QP-3473)": 78.494,
    "p_FR3ZSZWV10 (QP-3473)": 78.463,
    "p_853B4YQGHJ (QP-3089)": 78.537,
    "p_853B4YQGHP (QP-3089)": 78.459,
    "p_X8JBQTDZJP (QP-8265)": 78.497,
    "p_X8JBQTDZJT (QP-8265)": 78.752,
    "p_853B4YQGHM (QP-3089)": 73.23,  # confirmed fail
}
for name, h in heat_results.items():
    margin = (h - heat_thresh) / 0.25
    print(f"{name}: {h:.3f}°C {'✓' if h >= heat_thresh else '✗'} margin={margin:.2f} steps")

print()
print("=== PRIORITY: run water panels on heat-passing prototypes ===")
print("p_853B4YQGHJ (QP-3089): heat ✓ 78.537°C → need water + strength panels")
print("p_853B4YQGHP (QP-3089): heat ✓ 78.459°C → need water + strength panels")
print("p_SVC8TYAQGM (QP-7212): heat ✓ 78.626°C → need water + strength panels")
print("p_X8JBQTDZJP (QP-8265): heat ✓ 78.497°C → need water + strength panels")
print("p_X8JBQTDZJT (QP-8265): heat ✓ 78.752°C → need water + strength panels")
print()
print("p_H9Y5DQSD85 (QP-3089): water ✓ 81.21% → heat likely ~78.06°C ✗ FAILS REV B")
print("WARNING: my QP-3089 fix recipe probably fails heat under Rev B!")
