
# Analyze the new batch results
results2 = {
    'p_TF2B6S101T (QP-4476, lab_c)': 72.13,
    'p_TF2B6S101W (QP-4476, lab_c)': 72.25,
    'p_5C89S5B8FP (QP-7212, lab_c)': 78.30,
    'p_8JDCVCZNMF (QP-7212, lab_c)': 78.11,
    'p_B3MYV59B7T (QP-3089, lab_c)': 77.61,
    'p_B3MYV59B7W (QP-3089, lab_c)': 67.25,
    'p_47ZQZMDNXM (QP-6843, lab_b)': 63.69,
    'p_47ZQZMDNXP (QP-6843, lab_b)': 57.89,
    'p_47ZQZMDNXR (QP-6843, lab_b)': 62.74,
    'p_47ZQZMDNXT (QP-6843, lab_b)': 68.22,
    'p_VPVZP301DH (QP-3089, lab_b)': 78.19,
    'p_VPVZP301DK (QP-3089, lab_b)': 72.65,
    'p_VPVZP301DN (QP-3089, lab_b)': 78.36,
    'p_VPVZP301DQ (QP-3089, lab_b)': 78.55,
    'p_580QSJBKVQ (QP-7212, lab_b)': 78.47,
    'p_580QSJBKVS (QP-7212, lab_b)': 78.45,
    'p_580QSJBKVV (QP-7212, lab_b)': 78.27,
    'p_580QSJBKVX (QP-7212, lab_b)': 78.37,
    'p_6VJJE4M698 (QP-3473, lab_b)': 72.67,
    'p_6VJJE4M69A (QP-3473, lab_b)': 73.08,
    'p_6VJJE4M69C (QP-3473, lab_b)': 73.22,
    'p_6VJJE4M69E (QP-3473, lab_b)': 73.11,
    'p_J6CX8AHRR3 (QP-3473, lab_e)': 79.12,
    'p_J6CX8AHRR5 (QP-3473, lab_e)': 78.45,
}

HEAT_THRESH = 77.5
print("=== NEW HEAT EXPLORATORY RESULTS ===")
print("\nPASSING (≥77.5°C):")
for name, val in results2.items():
    if val >= HEAT_THRESH:
        print(f"  {name}: {val:.2f}°C ✓")
print("\nFAILING (<77.5°C):")
for name, val in results2.items():
    if val < HEAT_THRESH:
        print(f"  {name}: {val:.2f}°C ✗")

print("\n=== HEAT PANELS NEEDED (for qualification) ===")
print("Already paneled (from first batch):")
print("  QP-7212: p_SVC8TYAQGM, p_SVC8TYAQGR")
print("  QP-3473: p_FR3ZSZWV0T, p_FR3ZSZWV10")
print("  QP-3089: p_853B4YQGHJ, p_853B4YQGHP")
print("  QP-8265: p_X8JBQTDZJP, p_X8JBQTDZJT")
print()
print("NEW candidates needing heat panels (high priority):")
print("  QP-3473: p_J6CX8AHRR3 (79.12✓), p_J6CX8AHRR5 (78.45✓) [lab_e]")
print("  QP-3089: p_VPVZP301DH (78.19✓), p_VPVZP301DN (78.36✓), p_VPVZP301DQ (78.55✓) [lab_b]")
print("  QP-7212: p_580QSJBKVQ (78.47✓), p_580QSJBKVS (78.45✓), p_580QSJBKVV (78.27✓), p_580QSJBKVX (78.37✓) [lab_b]")
print("  QP-7212: p_5C89S5B8FP (78.30✓), p_8JDCVCZNMF (78.11✓) [lab_c]")
print("  QP-3089: p_B3MYV59B7T (77.61✓) [lab_c, borderline]")
print()
print("=== PL-57 SITUATION: STILL CRITICAL ===")
print("  QP-4476: lab_c also fails (~72°C). NO recipe passes heat except GG7 (blocked).")
print("  QP-6843: lab_b ALL FAIL BADLY (58-68°C).")
print("  Need lab_a's QP-6572 C5Q recipe that gave 77.76°C — must adapt to QP-4476/6843!")
