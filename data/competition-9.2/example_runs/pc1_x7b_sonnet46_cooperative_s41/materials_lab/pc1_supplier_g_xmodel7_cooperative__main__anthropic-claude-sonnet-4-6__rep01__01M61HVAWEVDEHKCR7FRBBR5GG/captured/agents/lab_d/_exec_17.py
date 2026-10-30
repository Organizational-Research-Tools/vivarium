
# Urgent analysis of Rev C situation
print("=== REVISION C ANALYSIS ===")
print()
print("Thresholds (Rev C):")
print("  Heat: ≥78.625°C  (base 77.5 + 4.5×0.25)")
print("  Strength: ≥7.235 kN/m  (base 7.10 + 4.5×0.03)")
print("  Water: ≥79.8%  (base 78.0 + 4.5×0.4)")
print()

print("=== QP-4476 GG7 RECIPE (p_PXAKTW39C3) — COMPLETE PANELS ===")
heat_g = 78.77925; str_g = 7.25351; wat_g = 81.6468
h_base=77.5; s_base=7.10; w_base=78.0
h_step=0.25; s_step=0.03; w_step=0.4
h_margin = (heat_g - h_base)/h_step
s_margin = (str_g - s_base)/s_step
w_margin = (wat_g - w_base)/w_step
weakest = min(h_margin, s_margin, w_margin)
print(f"  Heat: {heat_g}°C → margin {h_margin:.2f} steps {'✓' if heat_g>=78.625 else '✗'}")
print(f"  Strength: {str_g} kN/m → margin {s_margin:.2f} steps {'✓' if str_g>=7.235 else '✗'}")
print(f"  Water: {wat_g}% → margin {w_margin:.2f} steps {'✓' if wat_g>=79.8 else '✗'}")
print(f"  Weakest margin: {weakest:.2f} steps — PASSES Rev C (need 4.5)!")
print(f"  BLOCKER: Uses GG7 (PMLA prohibited)")
print()

print("=== BEST NON-GG7 RECIPE (P2G/3HW/8BB/...) on PL-95/PL-98 ===")
# QP-3089 best panels
h_no = 78.91550; s_no = 7.20986; w_no = 79.8648
h_m = (h_no - h_base)/h_step
s_m = (s_no - s_base)/s_step  
w_m = (w_no - w_base)/w_step
print(f"  Heat: {h_no}°C → margin {h_m:.2f} steps {'✓' if h_no>=78.625 else '✗'}")
print(f"  Strength: {s_no} kN/m → margin {s_m:.2f} steps {'✓' if s_no>=7.235 else '✗'} GAP={(7.235-s_no):.4f}")
print(f"  Water: {w_no}% → margin {w_m:.2f} steps {'✓' if w_no>=79.8 else '✗'} margin only {w_no-79.8:.3f}%!")
print()

print("=== LAB_F's QP-4476 NON-GG7 CANDIDATES (water already checked) ===")
print("  p_QHRB9W33WW (YX8): water 79.94% ✓, heat & strength UNKNOWN")
print("  p_QHRB9W33WY (5BU): water 80.11% ✓, heat & strength UNKNOWN")
print("  p_QHRB9W33X0 (3HW): water 80.87% ✓, heat & strength UNKNOWN")
print()
print("  GG7 adds ~2 steps per test:")
print(f"  Heat estimate (3HW): {heat_g - 2*h_step:.3f}°C vs threshold 78.625°C → {'passes' if heat_g-2*h_step>=78.625 else 'FAILS by '+str(round(78.625-(heat_g-2*h_step),3))+'°C'}")
print(f"  Strength estimate (3HW): {str_g - 2*s_step:.4f} kN/m vs threshold 7.235 → {'passes' if str_g-2*s_step>=7.235 else 'FAILS by '+str(round(7.235-(str_g-2*s_step),4))}")
print()
print("  CRITICAL: Heat estimate shows MARGINAL FAIL without GG7 boost")
print("  BUT: interactions may differ per secondary-sheet variant!")
print("  → MUST measure heat now to know for certain")
print()
print("=== PROGRAM SITUATION ===")
print("  PL-57: Only QP-4476 has any hope. Non-GG7 heat unknown. GG7 passes but PMLA violation.")
print("  PL-95: Recipe fails strength by 0.025 kN/m. Water margin razor-thin. Hard to fix in time.")
print("  PL-98: Same recipe, same strength problem.")
print()
print("IMMEDIATE ACTION: Run heat panels on p_QHRB9W33WW, p_QHRB9W33WY, p_QHRB9W33X0 NOW")
