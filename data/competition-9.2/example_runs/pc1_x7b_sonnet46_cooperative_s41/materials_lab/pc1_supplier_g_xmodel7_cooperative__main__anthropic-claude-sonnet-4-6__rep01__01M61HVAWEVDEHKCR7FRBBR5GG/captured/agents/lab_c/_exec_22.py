
# Calculate water mean for p_GR61XB2TYZ (QP-3089)
vals = [79.8640, 80.1732, 80.3624, 80.2936, 79.9016, 79.7052]
mean = sum(vals)/len(vals)
print(f"p_GR61XB2TYZ water mean: {mean:.4f}% — threshold 79.8% — {'PASS' if mean >= 79.8 else 'FAIL'}")
print(f"Receipts: r_Y3TSFAY740–r_Y3TSFAY745")
