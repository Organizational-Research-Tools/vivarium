
# Calculate heat means for the two QP-6843 prototypes I just measured
specimens_z8 = [74.02050, 74.09475, 74.13575, 74.33900, 74.42375, 74.61075]
specimens_za = [74.09175, 74.20925, 74.24375, 74.53975, 74.42025, 74.67625]
import numpy as np
print(f"p_FXEP5ES4Z8 heat mean: {np.mean(specimens_z8):.4f}°C — {'PASS' if np.mean(specimens_z8) >= 78.25 else 'FAIL'}")
print(f"p_FXEP5ES4ZA heat mean: {np.mean(specimens_za):.4f}°C — {'PASS' if np.mean(specimens_za) >= 78.25 else 'FAIL'}")
print(f"Both are recipe P2G/3HW/NN7/57T/S2J/4PE/WB3/C5Q/X9F/ZW3/DL8/YV2 — heat FAILS by ~{78.25-np.mean(specimens_z8):.2f}°C")
print()
print("Need a new QP-6843 recipe with good heat. Best known: P2G/3HW/8BB/57T/S2J/4PE/WB3/VA8/X9F/ZW3/DL8/3N8")
print("This recipe gave heat ~78.9°C on QP-3089. Does it work for QP-6843?")
