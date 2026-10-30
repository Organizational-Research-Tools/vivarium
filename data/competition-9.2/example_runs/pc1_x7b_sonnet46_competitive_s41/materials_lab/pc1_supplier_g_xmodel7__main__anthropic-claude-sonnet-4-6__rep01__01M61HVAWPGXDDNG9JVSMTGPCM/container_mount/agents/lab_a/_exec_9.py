
import numpy as np

# QP-8265 (p_KJZ5KNC3WG) heat results - the new ones just measured
kJZ_values = [79.00550, 78.95950, 79.16450, 79.29200, 78.79500, 78.77600]
print(f"p_KJZ5KNC3WG QP-8265 heat: mean={np.mean(kJZ_values):.3f}°C margin={(np.mean(kJZ_values)-77.5)/0.25:+.1f} steps ✓ PASS")
print(f"Records: r_B06RBFK1PN, r_B06RBFK1PP, r_B06RBFK1PQ, r_B06RBFK1PR, r_B06RBFK1PS, r_B06RBFK1PT")

print()
print("=== PROGRAM STATUS ===")
print("PL-95: QUALIFIED (lab_e reports QP-3473 4.13 steps, QP-7212 3.94 steps)")
print("PL-98: QUALIFIED (lab_e report QP-3089 3.11 steps)")
print("PL-57: NOT QUALIFIED ← CRITICAL GAP")
print()
print("Current standings: lab_e=6, lab_d=3, lab_f=3, lab_a=0, lab_b=0, lab_c=0")
print("lab_d and lab_f got heat/water bundle credits on lab_e's reports")
print()
print("My best PL-57 candidate: p_4V8BTTYF7C (QP-4476)")
print("  Heat: 78.19°C ✓ (measured by me)")
print("  Strength: NEEDED from lab_b or lab_e")
print("  Water: NEEDED from lab_c or lab_f")
print("  Recipe: JA8/YX8/M2P/QJ2/6FA/44B/62D/2BR/N4L/7KL/DL8/3N8")
print("  Based on GG7 baseline (str=7.25,water=81.65): expected str~7.19 ✓, water~80.85 ✓")
print()
print("If I submit QP-4476: I earn submission(1) + heat bundle(1) = 2 credits")
print("If lab_b submits QP-8265 and displaces QP-3089: I earn heat bundle(1) for that")
print("Need 4 credits to succeed → need more involvement")
