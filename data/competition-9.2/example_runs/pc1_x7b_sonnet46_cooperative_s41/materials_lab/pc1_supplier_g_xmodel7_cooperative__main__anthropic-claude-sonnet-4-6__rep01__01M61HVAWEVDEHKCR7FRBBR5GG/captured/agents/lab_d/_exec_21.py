
import numpy as np

# p_8F860GY05C (QP-3089, non-GG7 lab_b candidate)
h_8F860 = [78.58150, 78.74900, 78.86825, 78.29150, 78.34425, 78.38300]
mean_8F860 = np.mean(h_8F860)
print(f"p_8F860GY05C (QP-3089 non-GG7): mean heat = {mean_8F860:.4f}°C (threshold 78.625) → {'PASS' if mean_8F860 >= 78.625 else 'FAIL'}")

# p_ME2Y94BVSY (QP-3089, YV2 conditioning)
h_ME2Y = [78.57550, 78.66100, 78.78100, 78.29025, 78.34975, 78.46400]
mean_ME2Y = np.mean(h_ME2Y)
print(f"p_ME2Y94BVSY (QP-3089 YV2):     mean heat = {mean_ME2Y:.4f}°C (threshold 78.625) → {'PASS' if mean_ME2Y >= 78.625 else 'FAIL'}")

# p_8VNBERF1VK (QP-3473 GG7 recipe)
h_8VNB = [73.29725, 73.46350, 73.63000, 73.87675, 73.77900, 73.98400]
mean_8VNB = np.mean(h_8VNB)
print(f"p_8VNBERF1VK (QP-3473 GG7):     mean heat = {mean_8VNB:.4f}°C (threshold 78.625) → {'PASS' if mean_8VNB >= 78.625 else 'FAIL'}")
print(f"  → DEFICIT: {78.625 - mean_8VNB:.4f}°C BELOW threshold — CATASTROPHIC FAIL")
