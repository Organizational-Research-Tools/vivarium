
import numpy as np

heat_base = 77.5
heat_step = 0.25
heat_req = 78.625

# p_P68BNAVWAQ (QP-3473, pp1=4QB): 
panel_4QB_3473 = [73.00125, 73.10525, 73.27775, 73.25625, 72.88125, 72.91475]
mean_4QB = np.mean(panel_4QB_3473)
steps_4QB = (mean_4QB - heat_base) / heat_step

# p_P68BNAVWAS (QP-3473, pp1=UP5):
panel_UP5_3473 = [78.72450, 78.93125, 79.07950, 79.15125, 78.61925, 78.71875]
mean_UP5 = np.mean(panel_UP5_3473)
steps_UP5 = (mean_UP5 - heat_base) / heat_step

# p_02A6NY9WNR (QP-3473, 5BU secondary):
panel_5BU_3473 = [78.75025, 78.96775, 78.96875, 79.12800, 78.49150, 78.77275]
mean_5BU = np.mean(panel_5BU_3473)
steps_5BU = (mean_5BU - heat_base) / heat_step

# p_XDQFJKEVJX (QP-3089, N4L pp3):
panel_N4L = [74.00850, 74.08650, 74.14725, 74.38950, 73.84600, 73.90625]
mean_N4L = np.mean(panel_N4L)
steps_N4L = (mean_N4L - heat_base) / heat_step

print("=== HEAT PANEL RESULTS — JUST MEASURED ===")
print(f"p_P68BNAVWAQ QQ-3473 pp1=4QB: mean={mean_4QB:.3f}°C = {steps_4QB:.2f} steps → {'PASSES ✓' if steps_4QB>=4.5 else 'FAILS ✗ ← 4QB KILLS HEAT!'}")
print(f"p_P68BNAVWAS QQ-3473 pp1=UP5: mean={mean_UP5:.3f}°C = {steps_UP5:.2f} steps → {'PASSES ✓' if steps_UP5>=4.5 else 'FAILS ✗'}")
print(f"p_02A6NY9WNR QQ-3473 5BU sec: mean={mean_5BU:.3f}°C = {steps_5BU:.2f} steps → {'PASSES ✓' if steps_5BU>=4.5 else 'FAILS ✗'}")
print(f"p_XDQFJKEVJX QQ-3089 N4L pp3: mean={mean_N4L:.3f}°C = {steps_N4L:.2f} steps → {'PASSES ✓' if steps_N4L>=4.5 else 'FAILS ✗'}")
print()
print("⚠️ 4QB pp1 DROPS HEAT BY 5.8°C — CATASTROPHIC in P2G/YX8/8BB context!")
print("⚠️ p_WHE7SQ87ZZ (QQ-3473, 4QB pp1) will also be DEAD on heat!")
print("⚠️ p_2TK8W7BFC7 (QQ-3089, 4QB pp1) will also be DEAD on heat!")
print()
print("VIABLE PATHS:")
print(f"UP5 pp1 in QQ-3473: heat {mean_UP5:.3f}°C ({steps_UP5:.2f} steps ✓), water 80.12% ✓ — NEED STRENGTH")
print(f"5BU secondary in QQ-3473: heat {mean_5BU:.3f}°C ({steps_5BU:.2f} steps ✓), water 80.47% ✓ — NEED STRENGTH")
print(f"UP5 pp1 in QQ-3089 (p_2TK8W7BFC9): should give heat ~78.87°C ✓, water 80.12% ✓ — NEED HEAT+STRENGTH")
