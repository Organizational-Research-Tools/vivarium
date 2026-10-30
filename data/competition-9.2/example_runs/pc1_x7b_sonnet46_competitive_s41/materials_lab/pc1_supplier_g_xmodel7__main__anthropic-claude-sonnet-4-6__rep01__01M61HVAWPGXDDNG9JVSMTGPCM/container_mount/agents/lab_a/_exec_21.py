
# Compute heat means from just-measured panels
import numpy as np

# p_P68BNAVWAQ (pp1=4QB, QP-3473)
waq = [73.03500, 73.11500, 73.24650, 73.33675, 72.80950, 72.89375]
print(f"p_P68BNAVWAQ (pp1=4QB) heat mean: {np.mean(waq):.5f}°C  → {'PASS' if np.mean(waq)>=78.625 else 'FAIL'} Rev C")

# p_P68BNAVWAS (pp1=UP5, QP-3473)
was = [78.79000, 78.99275, 79.02125, 79.06525, 78.63475, 78.72050]
print(f"p_P68BNAVWAS (pp1=UP5) heat mean: {np.mean(was):.5f}°C  → {'PASS' if np.mean(was)>=78.625 else 'FAIL'} Rev C")
print(f"  Steps above threshold: {(np.mean(was)-77.5)/0.25:.2f}")

# p_P68BNAVWAV (pp1=WB3, 5BU secondary) = p_02A6NY9WNR already held
r_vals = [78.70575, 78.96925, 79.04150, 79.00625, 78.75375, 78.60250]
print(f"p_P68BNAVWAV/p_02A6NY9WNR heat mean: {np.mean(r_vals):.5f}°C  → {'PASS' if np.mean(r_vals)>=78.625 else 'FAIL'} Rev C")

print()
print("KEY FINDING: pp1=4QB in ZW3/X9F context kills heat (~73.07°C)!")
print("pp1=UP5 in ZW3/X9F context: heat 78.871°C — PASSES Rev C ✓")
print("p_WHE7SQ87ZZ (same recipe as p_P68BNAVWAQ) will FAIL heat at ~73°C")
