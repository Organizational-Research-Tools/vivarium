
# Critical assessment under Rev B
# p_853B4YQGHJ strength mean 7.164 kN/m vs new threshold 7.19 kN/m
print("=== CRITICAL: p_853B4YQGHJ strength vs Rev B ===")
strength_mean = 7.164
threshold = 7.19
print(f"Strength mean: {strength_mean} kN/m")
print(f"Threshold Rev B: {threshold} kN/m")
print(f"Result: {'PASS' if strength_mean >= threshold else 'FAIL'} by {(strength_mean-threshold)/0.03:.2f} steps")

print()
print("=== p_853B4YQGHJ recipe from lab_b note ===")
recipe = ["P2G", "5BU", "M2P", "R5N", "B3P", "4PE", "62D", "C5Q", "X9F", "5TZ", "57U", "6JZ"]
modules = ["base", "secondary", "binder", "AP1", "AP2", "AP3", "PP1", "PP2", "PP3", "surface", "joint", "conditioning"]
for m, v in zip(modules, recipe):
    print(f"  {m}: {v}")
print()
print("NOTABLE: joint=57U (we thought this always gives bad water!)")
print("BUT lab_f exploratory gave 79.69% water - passes Rev B threshold!")
print("Maybe P2G base + 57U joint can pass water unlike JA8/DA9 + 57U?")

print()
print("=== Heat-passing prototypes needing water panels (Rev B) ===")
candidates = [
    ("p_853B4YQGHJ", "QP-3089", 78.537, 7.164, "79.69% exploratory (lab_f)"),
    ("p_853B4YQGHP", "QP-3089", 78.459, None, "unknown"),
    ("p_SVC8TYAQGM", "QP-7212", 78.626, None, "unknown"),
    ("p_X8JBQTDZJP", "QP-8265", 78.497, None, "unknown"),
    ("p_X8JBQTDZJT", "QP-8265", 78.752, None, "unknown"),
]
for pid, proj, heat, strength, water in candidates:
    h_ok = "✓" if heat >= 78.25 else "✗"
    s_ok = "✓" if strength and strength >= 7.19 else ("✗" if strength else "?")
    print(f"{pid} ({proj}): heat={heat}°C {h_ok}, strength={strength if strength else '?'} {s_ok}, water={water}")
