
# Critical analysis of what just happened
# p_GR61XB2TYZ: "already held, no charge" — my measure call returned p_GR61XB2TZA records
# This means for p_GR61XB2TYZ, the system recognized I already held panel = p_GR61XB2TZA records
# But lab_b ran a FRESH panel on p_GR61XB2TYZ with new receipt IDs: r_QYKNNDRFXJ–r_QYKNNDRFXQ

# p_8VNBERF1VK (QP-3473): mean strength = ?
vals_8VNBERF1VK = [6.64550, 6.64577, 6.66065, 6.66701, 6.68699, 6.62828]
mean_8VNBERF = sum(vals_8VNBERF1VK)/6
print(f"p_8VNBERF1VK strength mean: {mean_8VNBERF:.5f} kN/m — threshold 7.235 — FAILS by {7.235-mean_8VNBERF:.5f}")
# This prototype is DEAD for QP-3473

# p_GR61XB2TZA (my prototype, QP-3089): I hold strength 6/6
vals_TZA = [7.22564, 7.25042, 7.25930, 7.27760, 7.28237, 7.22717]
mean_TZA = sum(vals_TZA)/6
print(f"p_GR61XB2TZA strength mean: {mean_TZA:.5f} kN/m — PASSES (mean {mean_TZA:.3f} > 7.235)")

# STATUS SUMMARY:
print("\n=== STATUS ===")
print("QP-3089 (PL-98):")
print(f"  p_GR61XB2TYZ: Heat 79.281°C ✓ (lab_d), Strength 7.254 kN/m ✓ (lab_b), Water: MISSING ← CRITICAL")
print(f"  p_GR61XB2TZA: Strength {mean_TZA:.3f} kN/m ✓ (lab_e), Heat: MISSING, Water: MISSING")
print()
print("QP-3473 (PL-95): GG7 recipe heat FAIL (73.672°C). Non-GG7 strength FAIL. LIKELY DEAD.")
print("QP-7212 (PL-95): Unknown — lab_a may have something.")
print()
print("ONLY ACTIONABLE TASK: Get water panel for p_GR61XB2TYZ from lab_c or lab_f NOW.")
print("Then lab_d or lab_a can submit QP-3089 report immediately.")
