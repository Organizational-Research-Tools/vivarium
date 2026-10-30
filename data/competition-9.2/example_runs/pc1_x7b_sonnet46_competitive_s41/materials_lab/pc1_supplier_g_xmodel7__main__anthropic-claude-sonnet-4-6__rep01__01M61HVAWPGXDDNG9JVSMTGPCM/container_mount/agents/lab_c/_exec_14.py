
import numpy as np

# Panel water results just measured
p_1HDVXQ4N6A_water = [71.1056, 71.3208, 71.2996, 71.4516, 71.7472, 71.7392]
p_8JN5B4DPHJ_water = [62.4328, 61.6760, 61.8440, 62.0200, 62.3780, 62.5708]
p_8JN5B4DPHM_water = [71.1544, 70.3324, 70.6208, 70.6656, 70.7408, 70.9644]

print("=== WATER PANEL RESULTS — PL-57 QP-4476 ===")
print(f"p_1HDVXQ4N6A (JA8/3HW/8BB/QJ2/6FA/44B/4QB/2BR/N4L/7KL/DL8/3N8):")
print(f"  Mean: {np.mean(p_1HDVXQ4N6A_water):.3f}% — FAILS (need ≥79.20%)")
print(f"  Gap: {np.mean(p_1HDVXQ4N6A_water) - 79.20:.2f}%")

print(f"\np_8JN5B4DPHJ (JA8/3HW/8BB/5FE/S2J/L6C/4QB/2BR/H3F/7TJ/9FU/YV2):")
print(f"  Mean: {np.mean(p_8JN5B4DPHJ_water):.3f}% — MASSIVE FAIL")
print(f"  Gap: {np.mean(p_8JN5B4DPHJ_water) - 79.20:.2f}%")

print(f"\np_8JN5B4DPHM (DA9/3HW/8BB/5FE/S2J/L6C/4QB/2BR/H3F/7TJ/9FU/YV2):")
print(f"  Mean: {np.mean(p_8JN5B4DPHM_water):.3f}% — FAILS")
print(f"  Gap: {np.mean(p_8JN5B4DPHM_water) - 79.20:.2f}%")

print("\n=== ANALYSIS ===")
print("The 8BB binder is the likely culprit for the water crash.")
print("Original p_4V8BTTYF7C (JA8/YX8/M2P/.../N4L) = 80.70% water — PASSES")
print("p_1HDVXQ4N6A changed binder M2P→8BB = 71.45% water — catastrophic drop")
print("Delta: {:.2f}%".format(np.mean(p_1HDVXQ4N6A_water) - 80.70))
print()
print("CONCLUSION: M2P binder required for PL-57 water. 8BB kills water in this context.")
print()
print("BUT: M2P + N4L recipe (p_4V8BTTYF7C/p_XV6JQRAVAV) gives strength ~6.55 kN/m (fails 7.19)")
print(f"Strength gap: {7.19 - 6.554:.3f} kN/m = {(7.19-6.554)/0.03:.1f} steps — HUGE")

print("\n=== QP-8265 exploratory ===")
print(f"p_D7ZRGS1PVJ water: 80.24% — PASSES ✓ (PL-98, strength pending from lab_b)")
