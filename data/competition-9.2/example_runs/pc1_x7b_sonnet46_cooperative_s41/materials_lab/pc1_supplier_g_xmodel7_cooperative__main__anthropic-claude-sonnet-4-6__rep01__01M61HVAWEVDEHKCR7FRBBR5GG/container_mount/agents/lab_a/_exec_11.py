
# IMMEDIATE IMPACT ANALYSIS of Revision B
# New thresholds: Heat ≥78.25°C, Strength ≥7.19 kN/m, Water ≥79.2%

print("=== REVISION B IMPACT ANALYSIS ===")
print("Base→New: Heat 77.5→78.25°C (+3 steps), Strength 7.1→7.19 kN/m (+3 steps), Water 78.0→79.2% (+3 steps)")

print("\n--- HEAT PANELS (my measurements) ---")
panels_heat = {
    'p_853B4YQGHJ (QP-3089)': 78.537,
    'p_853B4YQGHP (QP-3089)': 78.459,
    'p_FR3ZSZWV0T (QP-3473)': 78.494,
    'p_FR3ZSZWV10 (QP-3473)': 78.463,
    'p_SVC8TYAQGM (QP-7212)': 78.626,
    'p_SVC8TYAQGR (QP-7212)': 78.095,  # was close before, now FAILS
}
for p, h in panels_heat.items():
    margin_base = (h-77.5)/0.25
    status = f"✅ {margin_base:.1f} steps from base" if h >= 78.25 else f"❌ FAILS Rev B (only {margin_base:.1f} steps, need 3.0)"
    print(f"  {p}: {h:.3f}°C → {status}")

print("\n--- STRENGTH (known data) ---")
print("  p_853B4YQGHM (QP-3089): 7.210 kN/m → margin (7.21-7.1)/0.03=3.7 steps ✅ BUT heat fails!")
print("  p_853B4YQGHJ (QP-3089): 7.150 kN/m exploratory → margin 1.7 steps ❌ FAILS 7.19 threshold!")
print("  lab_b running strength PANEL on p_853B4YQGHJ now — result unknown")

print("\n--- WATER (known data) ---")
print("  p_853B4YQGHJ (QP-3089): 79.7% (exploratory) → margin (79.7-78.0)/0.4=4.25 steps ✅")
print("  p_SVC8TYAQGP (QP-7212): 80.5% → margin 6.25 steps ✅ (but heat 66.7°C fails!)")
print("  OLD GG7 water results 79.5-81.6% — most still pass 79.2%")

print("\n=== CRITICAL FAILURES UNDER REV B ===")
print("1. p_SVC8TYAQGR (QP-7212): heat 78.095°C < 78.25 → ELIMINATED")
print("2. p_853B4YQGHJ strength ~7.15 exploratory < 7.19 → likely ELIMINATED (awaiting panel)")
print("3. C5Q recipe on QP-6572 (77.76°C) → ELIMINATED (even this fails Rev B!)")
print("4. GG7-free QP-4476 (73.06°C) → way off, need ~+5.2°C boost")

print("\n=== WHAT STILL HAS A CHANCE ===")
print("PL-98 (QP-3089):")
print("  p_853B4YQGHJ: heat ✅, water likely ✅, strength PANEL pending (critical)")
print("  p_853B4YQGHP: heat ✅, strength/water unknown")
print("PL-95 (QP-7212/3473):")
print("  p_SVC8TYAQGM: heat ✅ (78.626°C), strength/water unknown")
print("  p_FR3ZSZWV0T/10: heat ✅ (~78.49/78.46°C), strength/water unknown")
print("PL-57 (QP-4476/6572/6843): NO KNOWN PASSING HEAT RECIPE WITHOUT GG7 UNDER REV B!")
print("  Best known without GG7: 77.76°C on QP-6572 (C5Q recipe) → fails 78.25°C")
print("  CRITICAL: Need to find new recipe approach for PL-57")

print("\n=== PL-57 STRATEGY ===")
print("Need heat ≥78.25°C without GG7. Options:")
print("A. Try C5Q as pp2 in GG7-base recipe (replace 2BR): JA8,3HW,M2P,QJ2,6FA,44B,62D,C5Q,N4L,7KL,DL8,3N8")
print("   - 3HW+2BR → 73.06°C; if C5Q adds ~5.2°C → 78.26°C (barely passes)")
print("   - C5Q has added +12°C in 4QB/JA8/3HW context → likely adds substantial amount here")
print("B. Try other secondary sheet variants (YX8, 5BU) in GG7-base recipe")
print("C. Also try for QP-6843 (project-specific effects are large)")
