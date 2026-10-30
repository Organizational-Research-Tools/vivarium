
import pandas as pd
import numpy as np

df = pd.read_csv('records.csv')

# New water thresholds: 79.2%
water_threshold_B = 79.2

# Check all water panels I hold
water_panels = df[df['kind'] == 'qualification'].copy()
if 'test' in water_panels.columns:
    water_panels = water_panels[water_panels['test'].str.contains('water', case=False, na=False)]

print("=== ALL WATER PANEL READINGS ===")
if not water_panels.empty:
    for proto in water_panels['prototype_id'].unique():
        grp = water_panels[water_panels['prototype_id'] == proto]
        mean = grp['value'].mean()
        project = grp['project'].iloc[0] if 'project' in grp.columns else '?'
        passes = "PASS" if mean >= water_threshold_B else "FAIL"
        print(f"{proto} ({project}): mean={mean:.4f}%, {passes} vs {water_threshold_B}%")
        if 'base_sheet' in grp.columns and grp['base_sheet'].notna().any():
            row = grp.iloc[0]
            pp1 = row.get('process_profile_1', '?')
            recipe_short = f"base={row.get('base_sheet','?')} pp1={pp1} pp3={row.get('process_profile_3','?')}"
            print(f"  {recipe_short}")
        print(f"  Receipts: {list(grp['record_id'])}")

print("\n=== HEAT INTERACTION ANALYSIS ===")
print("surface_treatment × process_profile_1 × process_profile_3 → HEAT")
print("JA8 recipe: 7KL × 62D × N4L → heat contribution unknown")
print("If pp1 changes to 4QB: 7KL × 4QB × N4L → different heat contribution")
print("Lab_b's claim that pp1 doesn't affect heat is WRONG!")

print("\n=== STRENGTH INTERACTION ANALYSIS ===")
print("process_profile_1 × additive_package_2 × additive_package_3 → STRENGTH")
print("JA8 recipe: 62D × 6FA × 44B → strength (current mean ~6.554 kN/m)")
print("If pp1→4QB: 4QB × 6FA × 44B → potentially +0.70 kN/m?")

print("\n=== REVISION B THRESHOLDS ===")
print(f"Heat: ≥ 78.25°C  (p_4V8BTTYF7C heat = 78.19°C → FAILS by 0.06°C)")
print(f"Strength: ≥ 7.19 kN/m  (p_4V8BTTYF7C strength = 6.554 kN/m → FAILS by 18+ steps)")
print(f"Water: ≥ 79.2%  (p_4V8BTTYF7C water = 80.70% → PASSES)")
print(f"\nQP-8265 (p_KJZ5KNC3WG): water mean = 79.198% → FAILS revision B threshold (79.2% required)")
print(f"QP-8265 (p_KJZ5KNC3WG): strength = 7.160 kN/m → FAILS revision B threshold (7.19 required)")
