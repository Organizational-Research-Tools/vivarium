
import numpy as np

# p_2TK8W7BFC9 (QP-3089, pp1=UP5) - already measured
p_2TK8W7BFC9 = [7.20779, 7.20923, 7.22129, 7.15940, 7.16900, 7.16969]
m = np.mean(p_2TK8W7BFC9)
print(f"p_2TK8W7BFC9 (QP-3089, pp1=UP5) strength: {m:.4f} kN/m  FAILS ({(m-7.235)/0.03:+.2f} steps)")
print()
print("p_MM0KRH0PJM (QP-7212, pp1=UP5): heat 78.860°C ✓, water 80.61% ✓")
print("Need strength panel NOW — still in my queue. Running immediately.")
print()
print("p_P68BNAVWAS (QP-3473, pp1=UP5) gave 6.516 kN/m — catastrophic")
print("p_2TK8W7BFC9 (QP-3089, pp1=UP5) gave 7.189 kN/m — recipe context matters")
print("QP-7212 recipe unknown — must try p_MM0KRH0PJM panel now")
