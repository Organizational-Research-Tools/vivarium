
# Summarize the new PL-57 results and think through next steps
print("=== NEW PL-57 STRENGTH RESULTS ===")
pl57_new = [
    ('QP-6843', 'p_QSB91XZG5B', 'L6C/4QB/VA8/X9F', 5.769),
    ('QP-6843', 'p_QSB91XZG5D', 'L6C/4QB/C5Q/X9F', 6.501),
    ('QP-6843', 'p_QSB91XZG5F', 'L6C/4QB/VA8/H3F', 6.473),
    ('QP-6572', 'p_18GEA2XWA3', 'L6C/4QB/VA8/X9F', 4.869),
    ('QP-6572', 'p_18GEA2XWA5', 'L6C/4QB/C5Q/X9F', 5.458),
    ('QP-4476', 'p_9890V7MW0H', 'L6C/4QB/VA8/X9F', 5.162),
    ('QP-4476', 'p_9890V7MW0K', 'L6C/4QB/C5Q/X9F', 5.835),
]
for proj, pid, desc, s in pl57_new:
    print(f"  {proj} {pid[:14]}: {s:.3f} kN/m ({'✓' if s>=7.10 else '✗'}  {(s-7.10)/0.03:+.1f} steps) [{desc}]")

print()
print("=== KEY INSIGHT: Comparing QP-6843 same recipe vs p_2H2TKFDYRQ ===")
print("  p_2H2TKFDYRQ: P2G/3HW/8BB/57T/S2J/L6C/4QB/2BR/H3F/ZW3/9FU/YV2 → 7.204 kN/m ✓")
print("  p_QSB91XZG5B: P2G/3HW/8BB/57T/S2J/L6C/4QB/VA8/X9F/ZW3/9FU/YV2 → 5.769 kN/m ✗")
print("  p_QSB91XZG5D: P2G/3HW/8BB/57T/S2J/L6C/4QB/C5Q/X9F/ZW3/9FU/YV2 → 6.501 kN/m ✗")
print("  p_QSB91XZG5F: P2G/3HW/8BB/57T/S2J/L6C/4QB/VA8/H3F/ZW3/9FU/YV2 → 6.473 kN/m ✗")
print()
print("CONCLUSION: 2BR (pp2) is critical for strength in QP-6843/PL-57.")
print("  2BR → VA8 : strength drops 7.20→5.77 (even with H3F kept → 6.47)")
print("  2BR → C5Q : strength drops 7.20→6.50 (with X9F) — slightly better")
print("  2BR (heat-failing pp2) appears strongly interaction-positive for PL-57 strength")
print()
print("=== WHAT WE KNOW ABOUT PL-57 HEAT ===")
print("  Lab_d: ALL lab_b PL-57 prototypes fail heat (best 74.17°C)")
print("  Lab_a: C5Q gives 77.76°C on QP-6572 — PASSES heat")
print("  Lab_d: C5Q+JA8 for QP-4476 fails heat ~73°C (but JA8 might be the problem!)")
print()
print("=== CRITICAL QUESTION: Does C5Q pass heat for QP-6843? ===")
print("  My p_QSB91XZG5D (QP-6843, P2G base + C5Q pp2) = strength 6.50 kN/m")
print("  If heat passes with C5Q on QP-6843, still need to fix strength from 6.50→7.10")
print("  Strength gap = 0.60 kN/m = 20 steps — large gap")
print()
print("=== OVERALL PROGRAM STATUS ===")
print("MY STRENGTH PANELS COMPLETED:")
print("  PL-95 p_J6CX8AHRR3 (QP-3473): mean 7.218 kN/m ✓ | needs heat+water panels")
print("  PL-95 p_S87ZV5EJH5 (QP-7212): mean 7.211 kN/m ✓ | needs heat+water panels")
print("  PL-98 p_YD1Q0XW9SA (QP-3089): mean 7.210 kN/m ✓ | needs heat+water panels")
print()
print("LAB_B HEAT-PASSING (need strength + water panels):")
print("  QP-7212: p_SVC8TYAQGM (78.63°C), p_SVC8TYAQGR (78.10°C)")
print("  QP-3473: p_FR3ZSZWV0T (78.49°C), p_FR3ZSZWV10 (78.46°C)")
print("  QP-3089: p_853B4YQGHJ (78.54°C), p_853B4YQGHP (78.46°C)")
print("  QP-8265: p_X8JBQTDZJP (78.50°C), p_X8JBQTDZJT (78.75°C)")
print()
print("=== NEXT ACTIONS ===")
print("1. Send urgent notes to lab_a/lab_d + lab_c/lab_f for panels on my 3 candidates")
print("2. Send note to lab_b: run strength panels on heat-passing prototypes")
print("3. Check if I have measurement access to lab_b's 8 heat-passing prototypes")
print("4. Create more PL-57 exploratories targeting different approaches for strength")
