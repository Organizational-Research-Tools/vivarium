
# Revision C impact analysis
base_heat = 77.50; step_heat = 0.25; rc_heat = 78.625
base_str = 7.10; step_str = 0.03; rc_str = 7.235
base_water = 78.00; step_water = 0.40; rc_water = 79.80

# Old standing reports
reports = [
    ("QP-3473/PL-95", 78.783, 7.224, 80.452),
    ("QP-7212/PL-95", 78.736, 7.218, 80.378),
    ("QP-3089/PL-98", 79.278, 7.193, 79.644),
]
print("=== REVISION C IMPACT ===")
print(f"Thresholds: heat≥{rc_heat}, strength≥{rc_str}, water≥{rc_water}")
for name, h, s, w in reports:
    hm = (h - base_heat)/step_heat
    sm = (s - base_str)/step_str
    wm = (w - base_water)/step_water
    wkst = min(hm, sm, wm)
    print(f"\n{name}: heat={h} ({hm:.2f}steps), str={s} ({sm:.2f}steps), water={w} ({wm:.2f}steps)")
    print(f"  Weakest={wkst:.2f} steps vs required 4.5. Heat{'✓' if h>=rc_heat else '✗'} Str{'✓' if s>=rc_str else '✗'} Water{'✓' if w>=rc_water else '✗'}")
    print(f"  Heat gap: {h-rc_heat:.3f}°C = {(h-rc_heat)/step_heat:.2f} steps")
    print(f"  Str gap: {s-rc_str:.3f} kN/m = {(s-rc_str)/step_str:.2f} steps")
    print(f"  Water gap: {w-rc_water:.3f}% = {(w-rc_water)/step_water:.2f} steps")

# p_8NVJHKV1KY (QP-4476 lead)
print("\n=== p_8NVJHKV1KY QP-4476 ===")
s = 7.19528
sm = (s - base_str)/step_str
print(f"Strength panel mean: {s:.5f} ({sm:.2f} steps). RevC needs 4.5 steps. Gap: {s-rc_str:.4f} kN/m = {(s-rc_str)/step_str:.2f} steps")
