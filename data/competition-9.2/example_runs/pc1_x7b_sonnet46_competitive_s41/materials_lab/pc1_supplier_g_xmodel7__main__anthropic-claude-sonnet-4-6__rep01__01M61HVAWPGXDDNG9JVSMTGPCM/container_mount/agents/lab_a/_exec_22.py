
import numpy as np

# p_2TK8W7BFC7 (QP-3089, pp1=4QB)
fc7 = [79.30200, 79.25100, 79.51675, 79.42625, 78.97100, 78.96250]
print(f"p_2TK8W7BFC7 (QP-3089, pp1=4QB) heat: {np.mean(fc7):.5f}°C → {'PASS ✓' if np.mean(fc7)>=78.625 else 'FAIL'}")

# p_2TK8W7BFC9 (QP-3089, pp1=UP5)
fc9 = [79.31225, 79.22775, 79.40250, 79.44100, 78.88350, 79.20300]
print(f"p_2TK8W7BFC9 (QP-3089, pp1=UP5) heat: {np.mean(fc9):.5f}°C → {'PASS ✓' if np.mean(fc9)>=78.625 else 'FAIL'}")

# p_MM0KRH0PJJ (QP-7212, pp1=4QB)
pjj = [72.70875, 72.80800, 72.93275, 73.06700, 72.64275, 72.71425]
print(f"p_MM0KRH0PJJ (QP-7212, pp1=4QB) heat: {np.mean(pjj):.5f}°C → {'PASS ✓' if np.mean(pjj)>=78.625 else 'FAIL'}")

# p_MM0KRH0PJM (QP-7212, pp1=UP5)
pjm = [78.79900, 78.82575, 79.06600, 79.13775, 78.64725, 78.68425]
print(f"p_MM0KRH0PJM (QP-7212, pp1=UP5) heat: {np.mean(pjm):.5f}°C → {'PASS ✓' if np.mean(pjm)>=78.625 else 'FAIL'}")
