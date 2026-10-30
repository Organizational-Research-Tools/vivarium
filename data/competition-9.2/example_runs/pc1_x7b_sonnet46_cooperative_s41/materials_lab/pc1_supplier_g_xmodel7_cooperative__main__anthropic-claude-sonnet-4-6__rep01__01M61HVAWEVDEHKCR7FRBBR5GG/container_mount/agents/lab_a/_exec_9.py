
# Analyze results immediately

# p_853B4YQGHM heat panel
heat_853M = [72.91225, 73.08425, 72.54250, 72.62125, 72.80450, 72.82025]
mean_853M = sum(heat_853M)/6
print(f"p_853B4YQGHM heat panel: mean={mean_853M:.3f}°C → {'PASS' if mean_853M>=77.5 else 'FAIL (need 77.5)'}")
print(f"  Shortfall: {mean_853M-77.5:.2f}°C ({(77.5-mean_853M)/0.25:.1f} steps)")

print("\n=== EXPLORATORY HEAT RESULTS ===")
results = {
    'p_GCXZZ91WJ2 (QP-6572)': 65.81,
    'p_GCXZZ91WJ4 (QP-6572)': 71.66,
    'p_GCXZZ91WJ6 (QP-6572)': 65.89,
    'p_GCXZZ91WJ8 (QP-6572)': 70.50,
    'p_SVC8TYAQGJ (QP-7212)': 73.67,
    'p_SVC8TYAQGM (QP-7212)': 78.21,  # PASSES!
    'p_SVC8TYAQGP (QP-7212)': 66.74,
    'p_SVC8TYAQGR (QP-7212)': 78.52,  # PASSES!
    'p_5ZPYV6MTWB (QP-3089)': 72.85,
    'p_853B4YQGHJ (QP-3089)': 78.68,  # PASSES! (same recipe as 6PWNP7BFF0 but different project!)
    'p_853B4YQGHP (QP-3089)': 78.39,  # PASSES!
    'p_6PWNP7BFEY (QP-6843)': 73.77,
    'p_6PWNP7BFF0 (QP-6843)': 68.25,  # FAILS (same recipe as 853J but QP-6843)
    'p_6PWNP7BFF2 (QP-6843)': 68.26,
    'p_6PWNP7BFF4 (QP-6843)': 68.05,
    'p_S1D13AXSXR (QP-4476)': 61.68,
    'p_S1D13AXSXT (QP-4476)': 66.79,
    'p_S1D13AXSXW (QP-4476)': 66.49,
    'p_S1D13AXSXY (QP-4476)': 72.39,
    'p_FR3ZSZWV0T (QP-3473)': 78.74,  # PASSES!
    'p_FR3ZSZWV0W (QP-3473)': 72.90,
    'p_FR3ZSZWV0Y (QP-3473)': 67.70,
    'p_FR3ZSZWV10 (QP-3473)': 78.88,  # PASSES!
}

for p, heat in results.items():
    status = "✅ PASSES" if heat >= 77.5 else f"❌ fails ({heat-77.5:.2f}°C)"
    print(f"  {p}: {heat:.2f}°C {status}")

print("\n=== KEY FINDINGS ===")
passes = [(p, h) for p, h in results.items() if h >= 77.5]
print(f"\nHeat PASSES ({len(passes)} prototypes):")
for p, h in passes:
    print(f"  {p}: {h:.2f}°C → margin {(h-77.5)/0.25:.1f} steps")

print("""
CRITICAL: p_853B4YQGHJ (QP-3089) passes heat at 78.68°C!
         p_853B4YQGHP (QP-3089) passes heat at 78.39°C!
         SAME recipe as p_6PWNP7BFF0 (QP-6843) which only gets 68.25°C → confirms PROJECT SPECIFICITY!
         
PL-95 BREAKTHROUGH: p_FR3ZSZWV0T and p_FR3ZSZWV10 (QP-3473) pass heat!
                    p_SVC8TYAQGM and p_SVC8TYAQGR (QP-7212) pass heat!
""")

print("\n=== STRENGTH STATUS ===")
print("p_853B4YQGHJ: strength 7.150 kN/m (lab_b exploratory?) - need panel confirmation")
print("p_853B4YQGHM: strength 7.21 kN/m (lab_b PANEL)")
print("Others: unknown")

print("\n=== WATER STATUS ===")
print("p_853B4YQGHJ: water 79.7% (lab_f) - is this a panel?")
print("p_853B4YQGHM: water 79.5% (lab_f)")
print("p_SVC8TYAQGP (QP-7212): water 80.5% (lab_f) - but heat only 66.74!")
print("Others: unknown")

print("\n=== PRIORITY PANEL LIST ===")
print("Need heat panels (already passing exploratory):")
priority_panels = [
    'p_853B4YQGHJ (QP-3089, 78.68°C) - MOST URGENT: need str+water panels too',
    'p_853B4YQGHP (QP-3089, 78.39°C) - backup',
    'p_FR3ZSZWV0T (QP-3473, 78.74°C) - PL-95',
    'p_FR3ZSZWV10 (QP-3473, 78.88°C) - PL-95',
    'p_SVC8TYAQGM (QP-7212, 78.21°C) - PL-95',
    'p_SVC8TYAQGR (QP-7212, 78.52°C) - PL-95',
    'p_8209SDK7SY (QP-4476, GG7-free, ~78.28°C expected) - PL-57',
]
for p in priority_panels:
    print(f"  {p}")
