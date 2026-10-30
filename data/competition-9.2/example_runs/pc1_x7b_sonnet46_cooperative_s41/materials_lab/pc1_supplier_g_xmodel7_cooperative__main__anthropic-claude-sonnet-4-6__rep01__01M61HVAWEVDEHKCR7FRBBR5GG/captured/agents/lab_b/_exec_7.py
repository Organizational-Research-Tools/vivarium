
# Revision B analysis
# New thresholds: heat >= 78.25°C, strength >= 7.19 kN/m, water >= 79.2%

print("=== REVISION B IMPACT ANALYSIS ===")
print("New thresholds: heat>=78.25°C, strength>=7.19 kN/m, water>=79.2%")
print()

# Key candidates and their known values
candidates = [
    # (name, project, heat, strength, water, heat_src, str_src, wat_src)
    ("p_853B4YQGHJ", "QP-3089", 78.537, 7.164, 79.69, "panel(lab_d)", "panel(lab_b)", "exploratory"),
    ("p_853B4YQGHP", "QP-3089", 78.459, None,  None,  "panel(lab_d)", "unknown", "unknown"),
    ("p_K81NZY79Q3", "QP-8265", 77.362, 7.263, 80.18, "panel", "panel", "panel"),
    ("p_TJTZMDX4AY", "QP-8265", 77.807, 7.197, 72.76, "panel", "panel", "panel"),
    ("p_A49NKYHQSB", "QP-8265", None,   None,  None,  "pending", "pending", "pending"),
    ("p_X8JBQTDZJT", "QP-8265", 78.752, 6.52,  79.73, "panel(lab_d)", "exploratory", "exploratory"),
    ("p_X8JBQTDZJP", "QP-8265", 78.497, 7.15,  70.86, "panel(lab_d)", "exploratory", "exploratory"),
    ("p_SVC8TYAQGM", "QP-7212", 78.626, 6.629, 71.71, "panel(lab_d)", "exploratory", "exploratory"),
    ("p_SVC8TYAQGR", "QP-7212", 78.095, 6.47,  70.26, "panel(lab_d)", "exploratory", "exploratory"),
    ("p_FR3ZSZWV0T", "QP-3473", 78.494, 5.782, None,  "panel(lab_d)", "exploratory", "unknown"),
    ("p_FR3ZSZWV10", "QP-3473", 78.463, 6.47,  None,  "panel(lab_d)", "exploratory", "unknown"),
]

HEAT_T = 78.25; STR_T = 7.19; WAT_T = 79.2

print(f"{'Prototype':<20} {'Project':<10} {'Heat':>7} {'Str':>7} {'Water':>7} {'H?':>4} {'S?':>4} {'W?':>4} {'ALL?'}")
print("-"*80)
for c in candidates:
    name, proj, h, s, w, hs, ss, ws = c
    hok = "✓" if h and h>=HEAT_T else ("✗" if h else "?")
    sok = "✓" if s and s>=STR_T else ("✗" if s else "?")
    wok = "✓" if w and w>=WAT_T else ("✗" if w else "?")
    all_ok = "✓" if (h and h>=HEAT_T and s and s>=STR_T and w and w>=WAT_T) else "✗"
    hs_str = f"{h:.2f}" if h else "  ?"
    ss_str = f"{s:.3f}" if s else "   ?"
    ws_str = f"{w:.1f}" if w else "  ?"
    print(f"{name:<20} {proj:<10} {hs_str:>7} {ss_str:>7} {ws_str:>7} {hok:>4} {sok:>4} {wok:>4} {all_ok:>4}")

print()
print("=== KEY FINDINGS ===")
print("p_853B4YQGHJ (QP-3089): Heat✓ (78.54) BUT STRENGTH FAILS (7.164 < 7.19 by 0.026 kN/m = 0.87 steps)")
print("p_853B4YQGHJ needs strength boost of ~0.87 steps to qualify under Rev B")
print()
print("p_K81NZY79Q3 (QP-8265): Heat FAILS (77.36 < 78.25), Str✓, Water✓")
print("p_TJTZMDX4AY (QP-8265): Heat FAILS (77.81 < 78.25), Str barely✓ (7.197), Water✗")
print()
print("QP-3089 v2 base: heat 78.54✓, water 79.69✓, only strength needs fixing")
print("QP-8265: ALL candidates fail heat under Rev B - need new high-heat recipe")
print()
print("PL-95 (QP-7212, QP-3473): All candidates fail strength badly (5.8-6.6 kN/m)")
print("PL-57 (QP-4476, QP-6572, QP-6843): All fail heat (<74°C)")
print()
print("=== RECIPE MODIFICATIONS TO TRY FOR QP-3089 ===")
print("Base: P2G, 5BU, M2P, R5N, B3P, 4PE, 62D, C5Q, X9F, 5TZ, 57U, 6JZ")
print("A: swap M2P->NN7 binder (NN7 positive for heat per lab_a, may boost strength)")
print("B: swap 4PE->44B AP3 (44B may improve strength; heat effect unknown for QP-3089)")  
print("C: swap both M2P->NN7 AND 4PE->44B")
print()
print("=== FOR QP-8265 ===")
print("Need heat >78.25°C. Only p_X8JBQTDZJT achieves this (78.75°C) but has U8H/YX8 base, low strength")
print("Try: JA8,3HW,NN7-based recipe (NN7 positive for heat), + high strength modules")
print("Try: JA8,3HW,NN7,QJ2,B3P,44B,4QB,C5Q,X9F,5TZ,57U,6JZ for QP-8265")
print()
print("=== FOR PL-57 ===")
print("Need heat >78.25°C AND strength >7.19 AND water >79.2%")
print("Lab_a's C5Q recipe gives 77.76°C for QP-6572 (still below 78.25 under Rev B!)")
print("Critical: NN7 binder + QJ2 AP1 + 44B AP3 + C5Q PP2 + X9F PP3 + 5TZ surface + 9FU joint")
