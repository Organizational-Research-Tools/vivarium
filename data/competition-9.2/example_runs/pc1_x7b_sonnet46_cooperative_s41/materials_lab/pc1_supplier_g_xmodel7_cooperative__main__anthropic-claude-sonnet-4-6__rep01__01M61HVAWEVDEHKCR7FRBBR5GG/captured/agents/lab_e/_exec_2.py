
# Design 12 diverse exploratory recipes (no GG7)
# Module order: base_sheet, sec_sheet, binder, addpkg1, addpkg2, addpkg3, 
#               procprof1, procprof2, procprof3, surface, joint, conditioning

# Variants (GG7 excluded from secondary sheet)
# base_sheet: JA8, P2G, DA9, U8H
# sec_sheet: 3HW, 5BU, YX8  (GG7 banned)
# binder: 8BB, M2P, NN7, T9M
# addpkg1: 5FE, R5N, 57T, QJ2
# addpkg2: 6FA, B3P, S2J, LD3
# addpkg3: L6C, 4PE, QJ4, 44B
# procprof1: 4QB, 62D, UP5, WB3
# procprof2: P8G, C5Q, VA8, 2BR
# procprof3: N7N, X9F, H3F, N4L
# surface: ZW3, 5TZ, 7KL, 7TJ
# joint: 9FU, 57U, DL8, 4GD
# conditioning: YV2, 6JZ, 3N8, G8Q

recipes = [
    # R1: all first variants
    ["JA8","3HW","8BB","5FE","6FA","L6C","4QB","P8G","N7N","ZW3","9FU","YV2"],
    # R2: all second variants (skipping GG7 -> use 5BU instead)
    ["P2G","5BU","M2P","R5N","B3P","4PE","62D","C5Q","X9F","5TZ","57U","6JZ"],
    # R3: all third variants
    ["DA9","YX8","NN7","57T","S2J","QJ4","UP5","VA8","H3F","7KL","DL8","3N8"],
    # R4: all fourth variants (sec_sheet=YX8 since GG7 is v2)
    ["U8H","YX8","T9M","QJ2","LD3","44B","WB3","2BR","N4L","7TJ","4GD","G8Q"],
    # R5: mix A - focus on last variants for strength-interacting modules
    ["JA8","5BU","T9M","QJ2","LD3","44B","WB3","VA8","H3F","7TJ","4GD","G8Q"],
    # R6: mix B
    ["U8H","3HW","NN7","5FE","S2J","QJ4","4QB","C5Q","N7N","7KL","9FU","3N8"],
    # R7: mix C
    ["DA9","YX8","8BB","R5N","6FA","L6C","62D","2BR","X9F","ZW3","57U","6JZ"],
    # R8: mix D
    ["P2G","5BU","M2P","57T","B3P","4PE","UP5","P8G","N4L","5TZ","DL8","YV2"],
    # R9: mix E - vary surface treatment heavily (affects 4 interactions)
    ["JA8","YX8","NN7","5FE","LD3","QJ4","62D","VA8","N7N","7TJ","57U","G8Q"],
    # R10: mix F 
    ["U8H","5BU","T9M","R5N","6FA","44B","UP5","C5Q","H3F","ZW3","DL8","6JZ"],
    # R11: mix G - different base/conditioning (affects 3 interactions)
    ["DA9","3HW","8BB","QJ2","B3P","L6C","WB3","2BR","X9F","5TZ","9FU","3N8"],
    # R12: mix H
    ["P2G","YX8","M2P","57T","S2J","4PE","4QB","P8G","N4L","7KL","4GD","YV2"],
]

projects = ["QP-6572", "QP-7212", "QP-3089"]

# Build batch for create_prototype: 12 recipes × 3 projects = 36 total
# We'll create per project separately (3 calls of 12)
for i, r in enumerate(recipes):
    print(f"R{i+1}: {r}")
    
print(f"\nTotal recipes: {len(recipes)}")
print(f"Total prototypes (3 projects): {len(recipes)*3}")
print("All use non-GG7 secondary sheet: ", all(r[1] != "GG7" for r in recipes))
