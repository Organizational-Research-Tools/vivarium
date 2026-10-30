
# PL-57 prototypes pending on my instrument
pl57_pending = [
    ('p_X9WN43AQ4V', 'QP-4476', 'lab_d'),  # heat 78.54°C = 4.16 steps above base
    ('p_X9WN43AQ4X', 'QP-4476', 'lab_d'),
    ('p_XV6JQRAVAS', 'QP-4476', 'lab_e'),
    ('p_XV6JQRAVAV', 'QP-4476', 'lab_e'),
    ('p_PHXDGYDJZ4', 'QP-4476', 'lab_b'),
    ('p_AJDCM7NSKX', 'QP-6843', 'lab_e'),
    ('p_AJDCM7NSKZ', 'QP-6843', 'lab_e'),
    ('p_KAZ5RD12DD', 'QP-6843', 'lab_b'),
    ('p_6D4GP1RVR9', 'QP-6572', 'lab_b'),
]
print("PL-57 prototypes to screen:")
for p, proj, lab in pl57_pending:
    print(f"  {p} ({proj}, from {lab})")
print(f"\nTotal exploratory reads: {len(pl57_pending)} units")
print("Revision B water threshold: 79.20% (need >= 79.20%)")
print("Promising if >= 79.20%")
