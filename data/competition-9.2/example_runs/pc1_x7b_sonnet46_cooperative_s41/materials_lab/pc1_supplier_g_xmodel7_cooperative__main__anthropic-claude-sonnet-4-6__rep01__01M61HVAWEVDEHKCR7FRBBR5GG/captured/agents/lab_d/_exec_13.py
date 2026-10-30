
import numpy as np

# New thresholds under Revision B
NEW_HEAT = 78.25    # was 77.5
NEW_STR  = 7.19     # was 7.10
NEW_WAT  = 79.2     # was 78.0

print("=== SPEC REVISION B IMPACT ANALYSIS ===")
print(f"New heat threshold: {NEW_HEAT}°C (was 77.5°C, +3 steps)")
print(f"New strength threshold: {NEW_STR} kN/m (was 7.10 kN/m, +3 steps)")
print(f"New water threshold: {NEW_WAT}% (was 78.0%, +3 steps)")
print()

# All known heat panel means
heat_panels = {
    'p_SVC8TYAQGM (QP-7212)': 78.626,
    'p_SVC8TYAQGR (QP-7212)': 78.095,   # NOW FAILS!
    'p_FR3ZSZWV0T (QP-3473)': 78.494,
    'p_FR3ZSZWV10 (QP-3473)': 78.463,
    'p_853B4YQGHJ (QP-3089)': 78.537,
    'p_853B4YQGHP (QP-3089)': 78.459,
    'p_X8JBQTDZJP (QP-8265)': 78.497,
    'p_X8JBQTDZJT (QP-8265)': 78.752,
    'p_J6CX8AHRR3 (QP-3473)': 78.734,
    'p_J6CX8AHRR5 (QP-3473)': 78.846,
    'p_VPVZP301DH (QP-3089)': 78.363,
    'p_VPVZP301DN (QP-3089)': 78.552,
    'p_VPVZP301DQ (QP-3089)': 78.294,   # BARELY passes (0.044°C margin)
    'p_580QSJBKVQ (QP-7212)': 78.635,
    'p_5C89S5B8FP (QP-7212)': 78.093,   # NOW FAILS!
}
print("=== HEAT PANELS: STATUS UNDER REVISION B ===")
for name, mean in heat_panels.items():
    status = "✓ PASS" if mean >= NEW_HEAT else "✗ NOW FAILS"
    margin = (mean - 77.5) / 0.25
    new_margin = (mean - NEW_HEAT) / 0.25
    print(f"  {name}: {mean:.3f}°C {status} (new margin: {new_margin:+.2f} steps)")

print()
# Known strength panels
strength_panels = {
    'p_6G7MJ89K4B (QP-4476, GG7)': 7.254,   # GG7 blocked
    'p_M9C39Z8Z9Z (QP-6843)': 7.194,
    'p_MYEZCT24GF (QP-6843)': 6.716,
    'p_YWCAXWQPBS (QP-3473)': 7.229,
    'p_P0EZCXYN8R (QP-7212)': 7.185,          # NOW FAILS!
    'p_DZWBS3SGG6 (QP-3089)': 6.402,
    'p_3GQVECBNN9 (QP-3089)': 6.731,
    'p_WHEF2Y691B (QP-3089)': 6.727,
    'p_SWSSAS3F5R (QP-3089)': 6.720,
    'p_RNDCCXYR4K (QP-8265)': 6.658,
}
print("=== STRENGTH PANELS: STATUS UNDER REVISION B ===")
for name, mean in strength_panels.items():
    status = "✓ PASS" if mean >= NEW_STR else "✗ FAILS"
    print(f"  {name}: {mean:.3f} kN/m {status}")

print()
# Known water panels
water_panels = {
    'p_WWXN5W4HZR (QP-4476, GG7)': 81.647,  # GG7 blocked
    'p_HMKH05YVYK (QP-4476)': 78.884,          # NOW FAILS!
    'p_M9C39Z8ZA8 (QP-6843)': 72.734,
    'p_MYEZCT24GR (QP-6843)': 69.266,
    'p_YWCAXWQPC2 (QP-3473)': 73.073,
    'p_20FMYAYEB0 (QP-7212)': 73.464,
    'p_DZWBS3SGGF (QP-3089)': 69.403,
    'p_9N4J1S2GVG (QP-3089)': 79.140,          # NOW FAILS!
    'p_QZDJSEWTA7 (QP-3089)': 79.089,          # NOW FAILS!
    'p_DQFXMS728H (QP-3089)': 78.997,          # NOW FAILS!
    'p_BQ5YN7X4H6 (QP-8265)': 79.032,          # NOW FAILS!
}
print("=== WATER PANELS: STATUS UNDER REVISION B ===")
for name, mean in water_panels.items():
    status = "✓ PASS" if mean >= NEW_WAT else "✗ FAILS"
    print(f"  {name}: {mean:.1f}% {status}")

print()
print("=== SUMMARY OF DAMAGE ===")
print("  Heat: p_SVC8TYAQGR (78.095) and p_5C89S5B8FP (78.093) NOW FAIL")
print("        p_VPVZP301DQ (78.294) barely passes — risky!")
print("  Strength: p_P0EZCXYN8R/QP-7212 (7.185) NOW FAILS. QP-6843 (7.194) barely passes.")
print("            ALL QP-3089 strength results (~6.73) far below 7.19 ✗")
print("  Water: ALL previous QP-3089 results (79.0-79.1%) NOW FAIL! Need >79.2%")
print("         QP-8265 water (79.032%) NOW FAILS!")
print("         ONLY GG7 recipe (81.647%) and old QP-3473 (73%) remain")
print()
print("  NO COMPLETE RECIPE currently qualifies under Revision B (without GG7)")
