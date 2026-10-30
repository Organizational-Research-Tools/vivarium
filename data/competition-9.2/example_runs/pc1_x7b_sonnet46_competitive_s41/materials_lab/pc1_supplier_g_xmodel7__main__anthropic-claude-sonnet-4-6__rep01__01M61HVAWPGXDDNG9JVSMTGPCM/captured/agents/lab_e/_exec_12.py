
# Analyze revision B impact on all known QP-6843 recipes
data = {
    "Recipe A (p_BNV031NMS0)": {"heat": 74.47175, "strength": 7.17020, "water": 78.9360},
    "Recipe B (p_KM74HN14JP)": {"heat": 74.50225, "strength": 7.20389, "water": 78.9852},
}

heat_base, heat_step = 77.5, 0.25
str_base, str_step = 7.10, 0.03
water_base, water_step = 78.0, 0.4
min_margin = 3.0

for name, vals in data.items():
    hm = (vals["heat"] - heat_base) / heat_step
    sm = (vals["strength"] - str_base) / str_step
    wm = (vals["water"] - water_base) / water_step
    weakest = min(hm, sm, wm)
    print(f"{name}:")
    print(f"  Heat margin: {hm:.2f} steps ({'PASS' if hm>=min_margin else 'FAIL'})")
    print(f"  Str  margin: {sm:.2f} steps ({'PASS' if sm>=min_margin else 'FAIL'})")
    print(f"  Water margin: {wm:.2f} steps ({'PASS' if wm>=min_margin else 'FAIL'})")
    print(f"  Weakest: {weakest:.2f} => {'QUALIFIES' if weakest>=min_margin else 'FAILS'}")
    print()

# What water % do we need under revision B?
print(f"New water threshold: {water_base + min_margin*water_step:.1f}%")
print(f"New heat  threshold: {heat_base + min_margin*heat_step:.2f}°C")
print(f"New str   threshold: {str_base + min_margin*str_step:.4f} kN/m")
print(f"\nGaps for Recipe B:")
rb = data["Recipe B (p_KM74HN14JP)"]
print(f"  Heat gap: {(heat_base + min_margin*heat_step) - rb['heat']:.2f}°C = {((heat_base + min_margin*heat_step) - rb['heat'])/heat_step:.1f} steps")
print(f"  Water gap: {(water_base + min_margin*water_step) - rb['water']:.3f}% = {((water_base + min_margin*water_step) - rb['water'])/water_step:.2f} steps")
