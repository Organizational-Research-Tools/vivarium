import numpy as np

# p_8NVJHKV1KY water panel results
water = [79.6360, 79.9340, 80.0712, 80.0784, 80.4112, 80.2916]
mean = np.mean(water)
margin_steps = (mean - 78.0) / 0.4  # base threshold is 78.0%
print(f"p_8NVJHKV1KY water panel mean: {mean:.4f}%")
print(f"Revision C threshold: 79.80%")
print(f"PASS: {mean >= 79.80}")
print(f"Margin above base (78.0%): {margin_steps:.2f} steps")
print(f"Margin above revision C (79.80%): {(mean-79.80)/0.4:.2f} steps")
print()
print("KEY: YV2 cond change vs 3N8 costs ~0.63% water (80.70→80.07%)")
print("Still passes revision C by 0.07% = 0.18 steps — very tight!")
print()
print("For L6C variant (p_CJXWSWQ72F): if L6C changes water interaction")
print("add_pkg2×joint×add_pkg3, water could drop below 79.80%")
print("Need panel urgently.")
