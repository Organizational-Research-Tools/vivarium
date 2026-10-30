
# Critical analysis of lab_b's strength results
print("=== LAB_B STRENGTH DATA: JA8/YX8/3N8 family ===")
data = [
    ("p_2XC47QDFKF", "JA8/YX8/M2P/4QB/2BR/N4L/7KL/3N8", 6.602),
    ("p_2XC47QDFKH", "JA8/YX8/M2P/WB3/2BR/N4L/7KL/3N8", 6.517),
    ("p_2XC47QDFKK", "JA8/YX8/M2P/4QB/P8G/N4L/7KL/3N8", 6.592),
    ("p_2XC47QDFKN", "JA8/YX8/M2P/4QB/VA8/N4L/7KL/3N8", 5.848),
    ("p_4V8BTTYF7C", "JA8/YX8/M2P/62D/2BR/N4L/7KL/3N8", 6.554),
]
for pid, recipe, s in data:
    margin = (s - 7.10) / 0.03
    revB_margin = (s - 7.19) / 0.03
    print(f"  {pid}: str={s:.3f} | base margin={margin:.1f} steps | Rev B margin={revB_margin:.1f} steps")

print()
print("All fail Rev B (need +3.0 steps = 7.19 kN/m)")
print("Root cause: cond×base×secondary = 3N8×JA8×YX8 (GG7 was giving +23 steps of strength)")
print()
print("=== NEW PATHS NEEDED ===")
print("Option 1: Change conditioning_step (3N8 → YV2, 6JZ, G8Q)")
print("  Changes cond×base×secondary AND cond×pp3×add1 (water) AND base×cond×joint (heat/str/water)")
print("  Risk: might hurt water (3N8×N4L×QJ2 might be good); might change heat")
print()
print("Option 2: DA9 base sheet with YV2 conditioning and YX8 secondary")
print("  p_X9WN43AQ4V (DA9/3HW/NN7/YV2): heat 78.64°C✓, strength 7.13 kN/m (-2 steps), water 63% ✗")
print("  Key: DA9/3HW/NN7 recipe gave str=7.13! Only 2 steps short!")
print("  Water failure likely from: B3P add2 (vs 6FA which gives 80.7%) AND NN7×N4L×DA9 interaction")
print("  Fix: DA9/YX8/M2P/QJ2/6FA/44B/xx/2BR/N4L/ZW3/DL8/YV2 - change binder+add2+secondary")
print()
print("Option 3: Lab_e's p_8NVJHKV1K* prototypes - unknown, need heat measurement")
print()
print("=== MY OWN NEW PROTOTYPES (registered) ===")
print("p_0GP2JB6HRG: JA8/YX8/M2P/4QB/2BR/N4L/7KL/3N8 — SAME recipe as p_2XC47QDFKF (str=6.602, DEAD)")
print("p_0GP2JB6HRJ: JA8/YX8/M2P/62D/2BR/N4L/ZW3/3N8 — ZW3 surface; str likely ~6.55 (DEAD on str)")
print("p_0GP2JB6HRM: JA8/YX8/M2P/4QB/2BR/N4L/ZW3/3N8 — ZW3; str likely ~6.60 (DEAD on str)")
print("p_0GP2JB6HRP: JA8/YX8/8BB/WB3/VA8/N4L/ZW3/3N8 — VA8 kills str; probably DEAD")
print("p_0GP2JB6HRR: JA8/YX8/8BB/4QB/VA8/N4L/ZW3/3N8 — VA8 kills str; probably DEAD")
print("p_KYWTMYWNGJ: JA8/YX8/M2P/4QB/VA8/N4L/ZW3/3N8 — VA8 kills str; probably DEAD")
print()
print("CONCLUSION: My registered prototypes likely all fail strength due to 3N8/VA8 issues.")
print("Need to register NEW prototypes with different conditioning_step!")
print()
print("=== PRIORITY NEW REGISTRATIONS ===")
new = [
    ("JA8", "YX8", "M2P", "QJ2", "6FA", "44B", "4QB", "2BR", "N4L", "ZW3", "DL8", "YV2"),
    ("JA8", "YX8", "M2P", "QJ2", "6FA", "44B", "4QB", "2BR", "N4L", "ZW3", "DL8", "6JZ"),
    ("JA8", "YX8", "M2P", "QJ2", "6FA", "44B", "4QB", "2BR", "N4L", "ZW3", "DL8", "G8Q"),
    ("DA9", "YX8", "M2P", "QJ2", "6FA", "44B", "4QB", "2BR", "N4L", "ZW3", "DL8", "YV2"),
    ("DA9", "YX8", "M2P", "QJ2", "6FA", "44B", "62D", "2BR", "N4L", "ZW3", "DL8", "YV2"),
    ("JA8", "YX8", "M2P", "QJ2", "6FA", "44B", "62D", "2BR", "N4L", "ZW3", "DL8", "YV2"),
]
for i, r in enumerate(new, 1):
    print(f"  {i}: {'/'.join(r)}")
