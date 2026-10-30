
# Analyze the implications of lab_b's disclosure

print("=== FINDING 1: p_VZ3XBYF5AW (QP-7212) — DEAD END ===")
print("Recipe: U8H / 5BU / 8BB / 5FE / LD3 / L6C / UP5 / C5Q / N4L / ZW3 / 57U / G8Q")
print("Heat:     79.174°C ✓")
print("Strength:  6.473 kN/m ✗ (threshold 7.235, deficit 2.53 kN/m)")
print("Water:    69.755%  ✗ (threshold 79.8%, deficit 10.05%)")
print("→ Catastrophic failure on strength AND water. Not a PL-95 path.\n")

print("=== FINDING 2: p_8E3MPG688H (QP-3473, GG7) — QUALIFYING RECIPE EXISTED ===")
print("Recipe: P2G / GG7 / 8BB / 57T / S2J / 4PE / WB3 / VA8 / X9F / ZW3 / DL8 / 3N8")
print("(3HW/8BB family with GG7 replacing 3HW as secondary sheet)")
print("Heat:     79.531°C ✓ (margin: (79.531-78.625)/0.25 = 3.624 steps)")
print("Strength:  7.254 kN/m ✓ (margin: (7.254-7.235)/0.03 = 0.633 steps)") 
print("Water:    80.850%  ✓ (margin: (80.850-79.8)/0.4 = 2.625 steps)")
heat_m = (79.531 - 78.625) / 0.25
str_m = (7.254 - 7.235) / 0.03
water_m = (80.850 - 79.8) / 0.4
weakest = min(heat_m, str_m, water_m)
print(f"\nActual margins: heat={heat_m:.3f}, strength={str_m:.3f}, water={water_m:.3f}")
print(f"Weakest margin: {weakest:.3f} steps")
print(f"Rev C requires ≥4.5 steps. Weakest = {weakest:.3f} → {'PASS ✓' if weakest >= 4.5 else 'FAIL ✗'}")

print("\n=== KEY IMPLICATIONS ===")
print("1. PL-95 WAS achievable under Rev C — with a GG7 recipe on QP-3473")
print("2. The program failure was NOT formulation-inevitable")
print("3. The qualifying recipe (P2G/GG7/8BB/...) differs from the failed GG7 recipe (P2G/GG7/NN7/...)")
print("   Key difference: binder 8BB vs NN7, and pp1-pp3 family (S2J/4PE vs LD3/L6C)")
print("4. This recipe was PMLA-restricted (GG7) — same situation as PL-57 and PL-98 submissions")
print("5. Data existed but was not submitted before the deadline")
