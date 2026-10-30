
# Strategy for Revision C — need strength ≥7.235, heat ≥78.625, water ≥79.8%
# Best strength booster: lab_b claims L6C (add3 change) gives +0.63 kN/m
# Alternative: surface=5TZ

# For QP-3473 (PL-95): 
#   Old: P2G/YX8/8BB/57T/S2J/4PE/WB3/VA8/X9F/ZW3/DL8/3N8
#   Need +0.011 kN/m on strength. Heat and water have good margins.
#   L6C variant: P2G/YX8/8BB/57T/S2J/L6C/WB3/VA8/X9F/ZW3/DL8/3N8
#   5TZ variant: P2G/YX8/8BB/57T/S2J/4PE/WB3/VA8/X9F/5TZ/DL8/3N8

# For QP-3089 (PL-98):
#   Old: same recipe, strength 7.193 (gap -1.40 steps), water 79.644 (gap -0.39 steps)
#   L6C variant: same — L6C affects add3×base×pp3 (strength+) and add2×joint×add3 (water?)

# For QP-4476 (PL-57):
#   Best: pp1=4QB+cond=YV2 gave 7.195. Need +1.32 steps more.
#   Add L6C: JA8/YX8/M2P/QJ2/6FA/L6C/4QB/2BR/N4L/7KL/DL8/YV2

# Module order: base, secondary, binder, add1, add2, add3, pp1, pp2, pp3, surface, joint, cond
prototypes = {
    "QP-3473 L6C": ["P2G","YX8","8BB","57T","S2J","L6C","WB3","VA8","X9F","ZW3","DL8","3N8"],
    "QP-7212 L6C": ["P2G","YX8","8BB","57T","S2J","L6C","WB3","VA8","X9F","ZW3","DL8","3N8"],
    "QP-3089 L6C": ["P2G","YX8","8BB","57T","S2J","L6C","WB3","VA8","X9F","ZW3","DL8","3N8"],
    "QP-4476 L6C": ["JA8","YX8","M2P","QJ2","6FA","L6C","4QB","2BR","N4L","7KL","DL8","YV2"],
    "QP-3473 5TZ": ["P2G","YX8","8BB","57T","S2J","4PE","WB3","VA8","X9F","5TZ","DL8","3N8"],
    "QP-3089 5TZ": ["P2G","YX8","8BB","57T","S2J","4PE","WB3","VA8","X9F","5TZ","DL8","3N8"],
}
for name, recipe in prototypes.items():
    print(f"{name}: {'/'.join(recipe)}")
