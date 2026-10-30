
# Revision C assessment: thresholds now at 4.5 steps above base
# Heat: ≥78.625°C, Strength: ≥7.235 kN/m, Water: ≥79.80%

print("=== REVISION C IMPACT ANALYSIS ===")
print("New thresholds: Heat≥78.625°C, Strength≥7.235 kN/m, Water≥79.80%")
print()

# Check all known recipes against revision C
recipes = {
    "p_YWF2FP1GRX (QP-3089, GG7)": (79.28125, 7.25375, 80.0500),
    "p_02A6NY9WNM (QP-3473, P2G/YX8/8BB/X9F)": (78.78250, 7.22390, 80.4520),
    "p_BZB62TCK50 (QP-7212, P2G/YX8/8BB/X9F)": (78.73625, 7.21835, 80.3780),
    "p_2058095Z34 (QP-3089, P2G/YX8/8BB/X9F)": (79.27775, 7.19333, 79.6444),
    "p_KJZ5KNC3WG (QP-8265)": (78.99875, 7.15985, 79.1980),
    "p_4V8BTTYF7C (QP-4476, JA8/YX8/M2P/N4L)": (78.19, 6.554, 80.70),
    "p_8NVJHKV1KY (QP-4476, +4QB+YV2)": (None, 7.195, None),  # heat/water unknown
    "p_5NEMM18WKP (QP-3473)": (78.64500, 6.54887, 79.8320),
    "p_AAY9VGT91F (QP-8265)": (74.25450, 7.20260, 78.9680),
}

heat_thr = 78.625
str_thr = 7.235
water_thr = 79.80

for name, (h, s, w) in recipes.items():
    h_ok = h is not None and h >= heat_thr
    s_ok = s is not None and s >= str_thr
    w_ok = w is not None and w >= water_thr
    if h is None: h_ok = "?"
    if s is None: s_ok = "?"
    if w is None: w_ok = "?"
    
    if all(x is True for x in [h_ok, s_ok, w_ok]):
        status = "✓ PASSES ALL"
    elif any(x is False for x in [h_ok, s_ok, w_ok]):
        status = "✗ FAILS"
    else:
        status = "? PARTIAL"
    
    print(f"{name}")
    print(f"  Heat: {h}°C {'✓' if h_ok is True else '✗' if h_ok is False else '?'} | Strength: {s} kN/m {'✓' if s_ok is True else '✗' if s_ok is False else '?'} | Water: {w}% {'✓' if w_ok is True else '✗' if w_ok is False else '?'} | {status}")

print()
print("=== ONLY CONFIRMED PASS UNDER REVISION C ===")
print("p_YWF2FP1GRX: Heat 79.28✓ Strength 7.254✓ Water 80.05✓ — uses GG7 (Association rule)")
print()
print("p_8NVJHKV1KY: strength 7.195 < 7.235 → FAILS revision C by 1.33 steps")
print("p_02A6NY9WNM: strength 7.224 < 7.235 → FAILS revision C by 0.37 steps")
print("p_BZB62TCK50: strength 7.218 < 7.235 → FAILS revision C by 0.57 steps")
print()
print("CONCLUSION: No known non-GG7 recipe passes ALL revision C thresholds.")
print("The only complete-panel qualifying recipe is p_YWF2FP1GRX (GG7, QP-3089).")
