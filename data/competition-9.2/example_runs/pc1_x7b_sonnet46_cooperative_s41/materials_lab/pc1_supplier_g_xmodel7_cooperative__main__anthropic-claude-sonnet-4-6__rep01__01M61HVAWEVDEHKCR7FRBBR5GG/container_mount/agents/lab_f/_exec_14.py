
# Revision C just hit. Recalculate everything.

# New thresholds
heat_base = 77.5; heat_step = 0.25; heat_min = 78.625
str_base = 7.1;   str_step = 0.03;  str_min = 7.235
wat_base = 78.0;  wat_step = 0.4;   wat_min = 79.8

# My QP-4476 water panels (just measured)
ww_vals = [80.4112, 80.3944, 80.6656, 80.7512, 80.9368, 81.0672]
wy_vals = [80.2592, 80.3688, 80.4356, 80.7448, 80.8584, 80.9116]
x0_vals = [80.1940, 80.1176, 80.3876, 80.5928, 80.8464, 81.0440]

for name, vals in [("p_QHRB9W33WW (YX8)", ww_vals),
                    ("p_QHRB9W33WY (5BU)", wy_vals),
                    ("p_QHRB9W33X0 (3HW)", x0_vals)]:
    mean = sum(vals)/len(vals)
    margin = (mean - wat_base) / wat_step
    print(f"{name}: water mean={mean:.3f}%, margin={margin:.2f} steps, pass={mean>=wat_min}")

print()

# Previously observed heat/strength on the P2G/VA8/X9F/ZW3 recipe family
# (QP-3473, QP-3089 prototypes p_J6CX8AHRR3, p_YD1Q0XW9SA)
heat_obs = [78.734, 78.916]  # two prototypes
str_obs  = [7.218, 7.210]    # two prototypes

for name, val in zip(["QP-3473 heat", "QP-3089 heat"], heat_obs):
    margin = (val - heat_base) / heat_step
    print(f"{name}: {val}°C, margin={margin:.2f} steps, pass Rev C={val>=heat_min}")
for name, val in zip(["QP-3473 strength", "QP-3089 strength"], str_obs):
    margin = (val - str_base) / str_step
    print(f"{name}: {val} kN/m, margin={margin:.2f} steps, pass Rev C={val>=str_min}")

print()
print("Rev C strength threshold:", str_min, "kN/m")
print("Rev C heat threshold:", heat_min, "°C")
print("Rev C water threshold:", wat_min, "%")
