
# Critical analysis under Revision C
# New thresholds: heat ≥78.625°C, strength ≥7.235 kN/m, water ≥79.8%
step = {"heat": 0.25, "strength": 0.03, "water": 0.4}
rev_c = {"heat": 78.625, "strength": 7.235, "water": 79.8}

data = {
    "QP-3089 p_YD1Q0XW9SA": {"heat": 78.9155, "strength": 7.20986, "water": 79.8648},
    "QP-3473 p_J6CX8AHRR3": {"heat": 78.734, "strength": 7.21811, "water": 80.3748},
    "QP-7212 p_S87ZV5EJH5": {"heat": 78.679, "strength": 7.21145, "water": 80.286},
}

print("=== WINNER RECIPE vs REV C THRESHOLDS ===")
for name, vals in data.items():
    margins = {k: (vals[k] - rev_c[k]) / step[k] for k in step}
    passes = all(v >= 0 for v in margins.values())
    print(f"\n{name}:")
    for k, m in margins.items():
        status = "✓" if m >= 0 else "✗ FAILS"
        print(f"  {k}: {vals[k]:.4f} (margin {m:.3f} steps) {status}")
    print(f"  → QUALIFIES: {passes}")

print("\n=== WHAT WE NEED ===")
print(f"Heat:     ≥{rev_c['heat']}°C")
print(f"Strength: ≥{rev_c['strength']} kN/m (winner gives ~7.210-7.218 → FAILS by 0.017-0.025 kN/m)")
print(f"Water:    ≥{rev_c['water']}% (QP-3089 at 79.865% barely passes, margin 0.16 steps)")
