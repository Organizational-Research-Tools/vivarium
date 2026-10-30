
import numpy as np

results = {
    # QP-6572 (PL-57)
    "QP-6572_v1": [4.92080, 4.82570, 4.83764],  # JA8, 3HW, 8BB, 5FE, 6FA, L6C, 4QB, P8G, N7N, ZW3, 9FU, YV2
    "QP-6572_v2": [6.34388, 6.38732, 6.38990],  # P2G, 5BU, M2P, R5N, B3P, 4PE, 62D, C5Q, X9F, 5TZ, 57U, 6JZ
    "QP-6572_v3": [5.10317, 5.10029, 5.07710],  # DA9, 5BU, NN7, 57T, S2J, QJ4, UP5, VA8, H3F, 7KL, DL8, 3N8
    "QP-6572_v4": [5.66372, 5.75741, 5.67659],  # U8H, YX8, T9M, QJ2, LD3, 44B, WB3, 2BR, N4L, 7TJ, 4GD, G8Q
    # QP-7212 (PL-95)
    "QP-7212_v1": [4.43738, 4.47332, 4.48751],
    "QP-7212_v2": [6.66749, 6.57986, 6.63740],
    "QP-7212_v3": [6.56144, 6.47954, 6.50702],
    "QP-7212_v4": [6.48107, 6.46676, 6.46883],
    # QP-3089 (PL-98)
    "QP-3089_v1": [7.18937, 7.19426, 7.22564],
    "QP-3089_v2": [7.14395, 7.11743, 7.18847],
    "QP-3089_v3": [7.21469, 7.24892, 7.26989],
    "QP-3089_v4": [6.65906, 6.57980, 6.63788],
}

threshold = 7.1
print(f"Strength threshold: {threshold} kN/m")
print(f"{'Recipe':<20} {'Mean':>8} {'vs threshold':>14} {'Status':>10}")
print("-" * 58)
for k, v in results.items():
    m = np.mean(v)
    diff = m - threshold
    steps = diff / 0.03
    status = "PASS ✓" if m >= threshold else "FAIL"
    print(f"{k:<20} {m:>8.4f} {diff:>+10.4f} ({steps:>+5.1f}s) {status:>6}")

print("\n=== KEY FINDINGS ===")
print("QP-3089 (PL-98): v1, v2, v3 all PASS strength!")
print("QP-6572 (PL-57): ALL FAIL — best is v2 at ~6.37 (gap: -0.73 kN/m, -24 steps)")
print("QP-7212 (PL-95): ALL FAIL — best is v2 at ~6.63 (gap: -0.47 kN/m, -16 steps)")
print()
print("Critical: Same recipe gives VERY different results across projects!")
print("  v1 on QP-3089: 7.20  vs  QP-6572: 4.86  vs  QP-7212: 4.46")
print("  → Projects have very different base strength levels")
print()
print("Action: Test OTHER projects in PL-57 and PL-95 lines to find better candidates")
print("Action: Immediately qualify QP-3089 (v3 looks best: ~7.24 kN/m)")
