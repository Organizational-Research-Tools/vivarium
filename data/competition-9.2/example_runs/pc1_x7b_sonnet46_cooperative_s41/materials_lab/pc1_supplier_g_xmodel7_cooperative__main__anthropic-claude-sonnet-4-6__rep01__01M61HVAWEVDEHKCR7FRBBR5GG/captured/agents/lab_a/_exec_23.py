
import numpy as np

# p_8F860GY05C heat
h1 = [78.54075, 78.65300, 78.74150, 78.23250, 78.56650, 78.48325]
m1 = np.mean(h1)
print(f"p_8F860GY05C (3N8): mean={m1:.4f}°C, threshold=78.625, {'✅ PASS' if m1>=78.625 else f'❌ FAIL (gap={78.625-m1:.4f}°C = {(78.625-m1)/0.25:.3f} steps)'}")
print(f"  margin from base: {(m1-77.5)/0.25:.3f} steps")

# p_ME2Y94BVSY heat  
h2 = [78.51750, 78.77100, 78.67625, 78.33125, 78.43300, 78.39250]
m2 = np.mean(h2)
print(f"p_ME2Y94BVSY (YV2): mean={m2:.4f}°C, threshold=78.625, {'✅ PASS' if m2>=78.625 else f'❌ FAIL (gap={78.625-m2:.4f}°C = {(78.625-m2)/0.25:.3f} steps)'}")
print(f"  margin from base: {(m2-77.5)/0.25:.3f} steps")

print("\nDIAGNOSIS: 4QB as pp1 (vs WB3) reduces heat by ~0.09-0.10°C (~0.35-0.42 steps)")
print("WB3 recipe gave 78.73-78.92°C; 4QB/C5Q/5TZ recipe gives 78.52-78.54°C")
print("Not enough to pass Rev C threshold of 78.625°C")
