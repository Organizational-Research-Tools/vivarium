
# Analyze strength panel results
results = {
    'QP-6572': {'proto': 'p_6D4GP1RVR9', 'values': [5.06180, 5.07377, 5.07458, 5.03705, 5.03483, 5.05079]},
    'QP-6843': {'proto': 'p_KAZ5RD12DD', 'values': [5.27627, 5.26355, 5.28131, 5.23355, 5.23103, 5.24591]},
    'QP-4476': {'proto': 'p_PHXDGYDJZ4', 'values': [4.52846, 4.54697, 4.54130, 4.49651, 4.50596, 4.52150]},
    'QP-7212': {'proto': 'p_VWGXN45KEP', 'values': [7.21316, 7.24505, 7.25852, 7.18226, 7.21130, 7.19981]},
    'QP-3473': {'proto': 'p_5626AZQYBH', 'values': [7.22762, 7.25957, 7.25033, 7.19090, 7.19453, 7.22045]},
    'QP-8607': {'proto': 'p_JJXGRVP079', 'values': [6.31136, 6.43187, 6.54017, 5.82539, 5.94878, 6.07781]},
    'QP-3089': {'proto': 'p_HQ697J921E', 'values': [7.20680, 7.20140, 7.22288, 7.16153, 7.18208, 7.18529]},
    'QP-8265': {'proto': 'p_KJZ5KNC3WG', 'values': [7.16423, 7.16972, 7.18898, 7.12421, 7.14410, 7.16786]},
}

product_lines = {
    'PL-57': ['QP-6572', 'QP-6843', 'QP-4476'],
    'PL-95': ['QP-7212', 'QP-3473', 'QP-8607'],
    'PL-98': ['QP-3089', 'QP-8265'],  # QP-7604 only exploratory
}

THRESHOLD = 7.10
STEP = 0.03

print("=== Strength Panel Results (recipe: P2G/YX8/8BB/57T/S2J/4PE/WB3/VA8/X9F/ZW3/DL8/3N8) ===")
print(f"{'Project':<12} {'Mean':>8} {'Pass?':>8} {'Margin(steps)':>15} {'PL'}")
print("-"*55)

for pl, projects in product_lines.items():
    for proj in projects:
        if proj in results:
            vals = results[proj]['values']
            mean = sum(vals)/len(vals)
            passed = mean >= THRESHOLD
            margin = (mean - THRESHOLD) / STEP
            print(f"{proj:<12} {mean:>8.4f} {'PASS' if passed else 'FAIL':>8} {margin:>15.2f} {pl}")

print("\n--- QP-7604 (PL-98) exploratory: 6.899 -> FAIL (below 7.10)")
print("\n=== Lab_e prototypes exploratory ===")
lab_e_results = {
    'QP-3473': [('p_02A6NY9WNM', 7.258), ('p_02A6NY9WNP', 7.230), ('p_02A6NY9WNR', 7.189)],
    'QP-7212': [('p_BZB62TCK50', 7.249), ('p_BZB62TCK52', 6.453)],
    'QP-3089': [('p_2058095Z34', 7.138), ('p_2058095Z36', 7.228)],
    'QP-4476': [('p_XV6JQRAVAS', 4.578), ('p_XV6JQRAVAV', 6.604)],
    'QP-6843': [('p_AJDCM7NSKX', 5.287), ('p_AJDCM7NSKZ', 5.916)],
    'QP-6572': [('p_CCG0G7KHZV', 5.035)],
    'QP-8607': [('p_HJ0BE1DW9Z', 6.247)],
    'QP-7604': [('p_VREAS4CDW2', 6.974)],
    'QP-8265': [('p_VRARQQZ7AR', 7.134)],
}
for proj, protos in lab_e_results.items():
    for pid, val in protos:
        passed = val >= THRESHOLD
        print(f"  {proj} {pid}: {val:.3f} {'PASS' if passed else 'FAIL'}")

print("\n=== CRITICAL FINDING ===")
print("PL-57 (QP-6572, QP-6843, QP-4476): ALL FAIL with lab_e recipe!")
print("Lab_e's own prototypes for PL-57 also all fail strength.")
print("Need to find a completely different recipe for PL-57.")
print("PL-95 passing: QP-7212, QP-3473 (QP-8607 fails)")
print("PL-98 passing: QP-3089, QP-8265 (QP-7604 fails)")
