
import numpy as np

panels = {
    'p_SVC8TYAQGM (QP-7212)': [78.58500, 78.63050, 78.71125, 78.90800, 78.37475, 78.54500],
    'p_SVC8TYAQGR (QP-7212)': [77.86675, 77.85425, 78.09675, 78.23900, 78.12350, 78.38975],
    'p_FR3ZSZWV0T (QP-3473)': [78.26975, 78.37000, 78.43600, 78.44675, 78.67275, 78.76875],
    'p_FR3ZSZWV10 (QP-3473)': [78.26550, 78.34000, 78.41225, 78.68500, 78.51975, 78.55250],
    'p_853B4YQGHJ (QP-3089)': [78.51825, 78.56725, 78.57000, 78.85425, 78.32875, 78.38050],
    'p_853B4YQGHP (QP-3089)': [78.24625, 78.26275, 78.41325, 78.61975, 78.64675, 78.56225],
    'p_X8JBQTDZJP (QP-8265)': [78.46275, 78.61500, 78.50875, 78.66100, 78.32175, 78.41125],
    'p_X8JBQTDZJT (QP-8265)': [78.44275, 78.67300, 78.73600, 78.77550, 78.89425, 78.99050],
}

HEAT_THRESH = 77.5
print("=== HEAT PANEL RESULTS (all 8 lab_b prototypes) ===")
for name, vals in panels.items():
    mean = np.mean(vals)
    status = "✓ PASS" if mean >= HEAT_THRESH else "✗ FAIL"
    print(f"  {name}: mean={mean:.3f}°C {status}")

print()
print("=== QP-4476 C5Q exploratory (JA8 base) ===")
c5q = {'p_JJ20J2VF6J': 72.79375, 'p_JJ20J2VF6M': 73.05250, 'p_JJ20J2VF6P': 73.13900}
for pid, val in c5q.items():
    print(f"  {pid}: {val:.2f}°C ✗ FAIL (C5Q does NOT rescue heat with JA8 base!)")

print()
print("=== PRODUCT LINE SITUATION ===")
print("  PL-57: ALL approaches failing heat. CRITICAL — need new strategy!")
print("    - lab_b's QP-4476/6572/6843 all fail heat (best 74.17°C)")
print("    - C5Q+JA8 recipe for QP-4476 gives ~73°C (same problem)")
print("    - lab_a's C5Q finding was for QP-6572 specifically at 77.76°C")
print("    - Must coordinate with lab_a immediately for PL-57")
print()
print("  PL-95: QP-7212 and QP-3473 have passing heat panels. Need strength+water.")
print("  PL-98: QP-3089 and QP-8265 have passing heat panels. Need strength+water.")
print()
print("  Best heat candidates for report submission:")
print("    QP-7212: p_SVC8TYAQGM (mean ~78.626°C, margin = (78.626-77.5)/0.25 ≈ 4.5 steps)")
print("    QP-3089: p_853B4YQGHJ (mean ~78.537°C, margin ≈ 4.1 steps)")
print("    QP-8265: p_X8JBQTDZJT (mean ~78.752°C, margin ≈ 5.0 steps)")
