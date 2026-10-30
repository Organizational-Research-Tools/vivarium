
import numpy as np

# Analyze Revision C impact
print("=== REVISION C ANALYSIS ===")
print("New thresholds: heat ≥78.625°C, strength ≥7.235 kN/m, water ≥79.8%")
print()

# 8BB binder heat verdict
print("CRITICAL FINDING — 8BB binder destroys heat on PL-57:")
print(f"  JA8/3HW/8BB: heat ~56.4°C (−87 steps) ← p_8JN5B4DPHJ")
print(f"  DA9/3HW/8BB: heat ~67.9°C (−43 steps) ← p_8JN5B4DPHM")
print(f"  P2G/3HW/8BB: heat ~74.2°C (−17 steps) ← p_YNCB6T4YAC")
print(f"  DA9/3HW/M2P: heat ~78.37°C (−1.0 steps from Rev C) ← p_DA8Y19F318")
print(f"  JA8/YX8/M2P: heat ~78.19°C (−1.7 steps from Rev C) ← p_4V8BTTYF7C")
print(f"  JA8/GG7/M2P: heat ~78.78°C (+0.6 steps from Rev C) ← p_WEMQRN3Q9M [GG7!]")
print()

# What's needed for Rev C
gap_heat = 78.625 - 78.19
gap_str = 7.235 - 7.195
gap_water = 79.8 - 80.7  # negative, water already passes for N4L recipes

print("Rev C gaps from best non-GG7 candidates:")
print(f"  p_8NVJHKV1KY (4QB+YV2): strength gap = +{gap_str:.3f} kN/m ({gap_str/0.03:.1f} steps)")
print(f"  JA8/YX8/M2P (base): heat gap = +{gap_heat:.3f}°C ({gap_heat/0.25:.1f} steps)")
print(f"  JA8/YX8/M2P (base): water gap (N4L) = {gap_water:.2f}% (passes ✓)")
print()

# PL-95/98 analysis
print("PL-95/98 gaps from lab_e's previous qualifying recipe:")
print(f"  QP-3473 strength: 7.224 vs 7.235 = gap {7.235-7.224:.3f} kN/m ({(7.235-7.224)/0.03:.1f} steps)")
print(f"  QP-7212 strength: 7.218 vs 7.235 = gap {7.235-7.218:.3f} kN/m ({(7.235-7.218)/0.03:.1f} steps)")
print(f"  Heat passes Rev C for PL-95/98 (was ~78.78°C > 78.625°C)")
print(f"  Water passes Rev C for PL-95/98 (was ~80.4% > 79.8%)")
print()

print("STRATEGY:")
print("1. p_8NVJHKV1KY heat panel — CRITICAL: does 4QB+YV2 push heat above 78.625°C?")
print("2. lab_b's p_CJXWSWQ72F (L6C variant) heat panel — L6C might boost both strength and heat")
print("3. PL-95/98: tiny strength gap (0.4-0.6 steps). 4QB+YV2 change (+0.64 kN/m on QP-4476)")
print("   may well close that gap. Registering PL-95/98 4QB+YV2 variants NOW.")
print("4. JA8/3HW/M2P recipe: GG7→3HW change. Heat likely ~78.28°C (−1.4 steps from Rev C).")
print("   Unlikely to pass Rev C on heat but worth confirming.")
