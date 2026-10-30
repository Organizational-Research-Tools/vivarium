
# Rapid impact analysis of Revision B
print("=== REVISION B IMPACT ANALYSIS ===")
print("New thresholds: Heat ≥78.25°C, Strength ≥7.19 kN/m, Water ≥79.2%")
print("(Old: Heat ≥77.5°C, Strength ≥7.10 kN/m, Water ≥78.0%)")
print()

# My strength panels
panels = [
    ('p_J6CX8AHRR3','QP-3473','PL-95',[7.21847,7.24592,7.24778,7.18259,7.19819,7.21571]),
    ('p_S87ZV5EJH5','QP-7212','PL-95',[7.21760,7.22954,7.25087,7.18019,7.19138,7.19912]),
    ('p_YD1Q0XW9SA','QP-3089','PL-98',[7.21376,7.22834,7.23722,7.17659,7.18844,7.21481]),
]
print("MY STRENGTH PANELS vs REVISION B (threshold 7.19 kN/m):")
for pid, proj, pl, vals in panels:
    mean = sum(vals)/6
    margin = (mean - 7.19) / 0.03
    status = f"✓ ({margin:+.2f} steps)" if mean >= 7.19 else f"✗ ({margin:+.2f} steps)"
    print(f"  {pid[:14]} ({proj},{pl}): mean={mean:.4f} kN/m {status}")

print()
print("LAB_D HEAT PANELS vs REVISION B (threshold 78.25°C):")
lab_d_heat = [
    ('p_SVC8TYAQGM','QP-7212','PL-95',78.626),
    ('p_SVC8TYAQGR','QP-7212','PL-95',78.095),
    ('p_FR3ZSZWV0T','QP-3473','PL-95',78.494),
    ('p_FR3ZSZWV10','QP-3473','PL-95',78.463),
    ('p_853B4YQGHJ','QP-3089','PL-98',78.537),
    ('p_853B4YQGHP','QP-3089','PL-98',78.459),
    ('p_X8JBQTDZJP','QP-8265','PL-98',78.497),
    ('p_X8JBQTDZJT','QP-8265','PL-98',78.752),
]
for pid, proj, pl, heat in lab_d_heat:
    margin = (heat - 78.25) / 0.25
    status = f"✓ ({margin:+.2f} steps)" if heat >= 78.25 else f"✗ ({margin:+.2f} steps)"
    print(f"  {pid[:14]} ({proj},{pl}): {heat:.3f}°C {status}")

print()
print("WATER — OLD PASSING CANDIDATES vs REVISION B (threshold 79.2%):")
print("  QP-3473 GG7 winner p_8E3MPG688H: 80.85% → STILL PASSES (4.1 steps) [but GG7]")
print("  QP-3473 X9F recipes (lab_f data): 79-80% → MARGINAL — may be <79.2% sometimes!")
print("  OLD QP-3089 p_9N4J1S2GVS: water 78.48% → NOW FAILS under rev B (was 78.48 > 78.0)")
print("  QP-7212 N7N recipes: 73.45% → FAILS badly (no change)")
print()
print("CRITICAL CONCERN: Water threshold jump to 79.2% threatens X9F recipes.")
print("  Lab_f reported X9F gives 79-80%. If range is 79.0-79.2, many now fail!")
print("  The GG7 winner at 80.85% water was well above; non-GG7 recipe may be different.")
print()
print("PROGRAM STATUS:")
print("  PL-95: Need heat+water panels on p_J6CX8AHRR3 or p_S87ZV5EJH5")
print("  PL-98: Need heat+water panels on p_YD1Q0XW9SA (or lab_b J/P prototypes)")
print("  PL-57: Still no candidate passing both strength AND heat")
print()
print("TIME: 30 min remaining — every minute counts!")
