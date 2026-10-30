
# Compute panel means
import numpy as np

tt7 = [7.23239, 7.21778, 7.24025, 7.17863, 7.18847, 7.20164]
kd3 = [7.20521, 7.24073, 7.22231, 7.19375, 7.20236, 7.20434]
xbg = [7.37399, 7.39904, 7.40456, 7.35005, 7.36349, 7.36451]
xbj = [7.33754, 7.34540, 7.36292, 7.36610, 7.38590, 7.40270]

for name, vals in [("p_TT7GNA1YZS (QP-3089)", tt7), ("p_KD3TGB68DX (QP-7212)", kd3),
                    ("p_57M2N73XBG (QP-3089)", xbg), ("p_57M2N73XBJ (QP-3089)", xbj)]:
    m = np.mean(vals)
    diff = m - 7.235
    steps = diff / 0.03
    print(f"{name}: mean={m:.4f} kN/m, diff={diff:+.4f} ({steps:+.2f} steps) {'✓ PASSES' if m>=7.235 else '✗ FAILS'}")
