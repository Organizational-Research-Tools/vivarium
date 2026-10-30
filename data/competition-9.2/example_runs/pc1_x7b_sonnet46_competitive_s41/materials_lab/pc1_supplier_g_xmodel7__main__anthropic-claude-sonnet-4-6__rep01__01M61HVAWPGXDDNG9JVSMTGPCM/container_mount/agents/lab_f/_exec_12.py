
import numpy as np

print("=== REVISION B IMPACT ANALYSIS ===")
print("New thresholds: heat >= 78.25°C, strength >= 7.19 kN/m, water >= 79.20%")
print()

# p_4V8BTTYF7C (QP-4476)
heat_4476 = 78.19
water_4476_vals = [80.4112, 80.3944, 80.6656, 80.7512, 80.9368, 81.0672]
print(f"p_4V8BTTYF7C (QP-4476):")
print(f"  Heat:     {heat_4476}°C vs threshold 78.25°C => FAILS by {78.25-heat_4476:.3f}°C = {(78.25-heat_4476)/0.25:.2f} steps DEAD")
print(f"  Water:    {np.mean(water_4476_vals):.3f}% vs threshold 79.20% => margin {(np.mean(water_4476_vals)-79.20)/0.40:.2f} steps ✓")
print()

# p_KJZ5KNC3WG (QP-8265) 
water_8265_vals = [79.5720, 79.4548, 78.8336, 78.9728, 79.0252, 79.3296]
str_8265 = 7.16
print(f"p_KJZ5KNC3WG (QP-8265):")
print(f"  Water:    {np.mean(water_8265_vals):.4f}% vs threshold 79.20% => {'FAILS' if np.mean(water_8265_vals)<79.20 else 'PASSES'} by {np.mean(water_8265_vals)-79.20:.4f}%")
print(f"  Strength: {str_8265} kN/m vs threshold 7.19 kN/m => FAILS by {7.19-str_8265:.3f} kN/m = {(7.19-str_8265)/0.03:.1f} steps DEAD")
print()

# Existing standing reports (grandfathered)
print("=== EXISTING STANDING REPORTS (grandfathered - still qualify) ===")
print("QP-3473: margin 4.13 steps (>3) ✓ stays")
print("QP-7212: margin 3.94 steps (>3) ✓ stays")
print("QP-3089: margin 3.11 steps (>3) ✓ stays")
print()

print("=== WHAT STILL NEEDS QUALIFYING ===")
print("PL-57: NOTHING qualified yet - needs recipe beating ALL new thresholds")
print("Need: heat >=78.25, strength >=7.19, water >=79.20")
print()
print("Lab_e H3F approach water: ~78.94-78.99% < 79.20% => ALSO fails revision B water!")
print("Lab_d's QP-4476 prototypes (p_X9WN43AQ4V, p_X9WN43AQ4X): unknown - must test")
