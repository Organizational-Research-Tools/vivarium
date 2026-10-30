
# Analyze lab_e's insight:
# GG7 recipe QP-3473: P2G/GG7/8BB/57T/S2J/4PE/WB3/VA8/X9F/ZW3/DL8/3N8
# Results: heat=79.53, strength=7.25, water=80.85 (per lab_e)
# My own QP-4476 GG7 recipe: JA8/GG7/M2P/QJ2/6FA/44B/62D/2BR/N4L/7KL/DL8/3N8
# Results: heat=78.78, strength=7.25, water=81.65 (from my_records)
# GG7 adds ~2 spec steps to each test

heat_step = 0.25
str_step = 0.03
water_step = 0.4
gg7_steps = 2

# Non-GG7 projections for lab_e's recipe
heat_gg7 = 79.53; str_gg7 = 7.25; water_gg7 = 80.85
heat_nogg7 = heat_gg7 - gg7_steps * heat_step
str_nogg7 = str_gg7 - gg7_steps * str_step
water_nogg7 = water_gg7 - gg7_steps * water_step

print("Lab_e's recipe - non-GG7 projection (replacing GG7 with YX8):")
print(f"  Heat:     {heat_nogg7:.2f}°C  (threshold 77.5) → {'PASS' if heat_nogg7 >= 77.5 else 'FAIL'}")
print(f"  Strength: {str_nogg7:.3f} kN/m (threshold 7.1)  → {'PASS' if str_nogg7 >= 7.1 else 'FAIL'}")
print(f"  Water:    {water_nogg7:.2f}%   (threshold 78.0) → {'PASS' if water_nogg7 >= 78.0 else 'FAIL'}")

margins = [(heat_nogg7 - 77.5)/heat_step, (str_nogg7 - 7.1)/str_step, (water_nogg7 - 78.0)/water_step]
print(f"  Weakest margin: {min(margins):.2f} steps")

print()
# Non-GG7 projections for my QP-4476 GG7 recipe
heat_gg7b = 78.78; str_gg7b = 7.25; water_gg7b = 81.65
heat_nogg7b = heat_gg7b - gg7_steps * heat_step
str_nogg7b = str_gg7b - gg7_steps * str_step
water_nogg7b = water_gg7b - gg7_steps * water_step

print("My QP-4476 GG7 recipe - non-GG7 projection (replacing GG7 with YX8):")
print(f"  Heat:     {heat_nogg7b:.2f}°C  → {'PASS' if heat_nogg7b >= 77.5 else 'FAIL'}")
print(f"  Strength: {str_nogg7b:.3f} kN/m → {'PASS' if str_nogg7b >= 7.1 else 'FAIL'}")
print(f"  Water:    {water_nogg7b:.2f}%   → {'PASS' if water_nogg7b >= 78.0 else 'FAIL'}")

margins_b = [(heat_nogg7b - 77.5)/heat_step, (str_nogg7b - 7.1)/str_step, (water_nogg7b - 78.0)/water_step]
print(f"  Weakest margin: {min(margins_b):.2f} steps")

print()
print("Target recipe (non-GG7 version of lab_e's formula):")
print("P2G, YX8, 8BB, 57T, S2J, 4PE, WB3, VA8, X9F, ZW3, DL8, 3N8")
print()
print("Backup recipe (non-GG7 version of my QP-4476 formula):")
print("JA8, YX8, M2P, QJ2, 6FA, 44B, 62D, 2BR, N4L, 7KL, DL8, 3N8")
