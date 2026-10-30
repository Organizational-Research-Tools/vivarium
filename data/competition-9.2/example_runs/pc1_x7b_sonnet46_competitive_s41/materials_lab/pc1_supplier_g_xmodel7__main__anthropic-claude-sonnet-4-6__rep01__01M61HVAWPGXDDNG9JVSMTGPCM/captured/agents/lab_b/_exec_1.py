
# Analyze the lab situation and plan strategy
import itertools
import random

# Module structure
modules = [
    ("base sheet", ["JA8", "P2G", "DA9", "U8H"]),
    ("secondary sheet", ["3HW", "GG7", "5BU", "YX8"]),  # GG7 is banned
    ("binder system", ["8BB", "M2P", "NN7", "T9M"]),
    ("additive package 1", ["5FE", "R5N", "57T", "QJ2"]),
    ("additive package 2", ["6FA", "B3P", "S2J", "LD3"]),
    ("additive package 3", ["L6C", "4PE", "QJ4", "44B"]),
    ("process profile 1", ["4QB", "62D", "UP5", "WB3"]),
    ("process profile 2", ["P8G", "C5Q", "VA8", "2BR"]),
    ("process profile 3", ["N7N", "X9F", "H3F", "N4L"]),
    ("surface treatment", ["ZW3", "5TZ", "7KL", "7TJ"]),
    ("joint system", ["9FU", "57U", "DL8", "4GD"]),
    ("conditioning step", ["YV2", "6JZ", "3N8", "G8Q"]),
]

# Generate diverse exploratory recipes
# Strategy: Use all first variants as baseline, then vary each module
# Avoid GG7 (secondary sheet variant 2)

def gen_recipe(indices):
    """Generate recipe from list of variant indices (0-3) for each module"""
    recipe = []
    for i, (name, variants) in enumerate(modules):
        recipe.append(variants[indices[i]])
    return recipe

# Baseline: all first variants
baseline = [0]*12
print("Baseline:", gen_recipe(baseline))

# Create diverse recipes by varying combinations
random.seed(42)
recipes_to_test = []

# Add baseline
recipes_to_test.append(baseline[:])

# Add recipes varying one module at a time (but skip GG7)
for module_idx in range(12):
    for variant_idx in range(4):
        if module_idx == 1 and variant_idx == 1:  # Skip GG7
            continue
        if variant_idx == 0:  # Skip baseline
            continue
        r = baseline[:]
        r[module_idx] = variant_idx
        recipes_to_test.append(r)

# Add some fully random recipes
for _ in range(20):
    r = [random.randint(0, 3) for _ in range(12)]
    if r[1] == 1:  # Avoid GG7
        r[1] = random.choice([0, 2, 3])
    recipes_to_test.append(r)

print(f"\nTotal recipes to test: {len(recipes_to_test)}")
print("\nFirst few recipes:")
for i, r in enumerate(recipes_to_test[:5]):
    print(f"  Recipe {i}: {gen_recipe(r)}")

# Key interactions to understand
print("\n\nKey interactions affecting each test:")
print("HEAT: surface_treatment×process_profile1×process_profile3, secondary_sheet×surface_treatment×binder_system, surface_treatment×binder_system×process_profile2, additive_pkg1×process_profile2×conditioning_step, additive_pkg3×base_sheet×process_profile3, base_sheet×conditioning_step×joint_system")
print("STRENGTH: conditioning_step×base_sheet×secondary_sheet, additive_pkg3×base_sheet×process_profile3, surface_treatment×process_profile3×additive_pkg2, surface_treatment×binder_system×process_profile2, process_profile1×additive_pkg2×additive_pkg3, base_sheet×conditioning_step×joint_system")
print("WATER: additive_pkg2×joint_system×additive_pkg3, additive_pkg3×base_sheet×process_profile3, conditioning_step×process_profile3×additive_pkg1, surface_treatment×binder_system×process_profile2, process_profile3×binder_system×base_sheet, base_sheet×conditioning_step×joint_system")

print("\n\nCredit strategy:")
print("- Submit reports to earn 1 credit per project")
print("- Produce majority of strength receipts to earn strength bundle credit")
print("- Collaborate with heat (lab_a/lab_d) and water (lab_c/lab_f) labs")
print("- Need 4+ credits to succeed")
print("- Each qualified project: 4 credits (1 submitter + 1 heat + 1 strength + 1 water)")
print("- If I submit AND do most strength readings: I get 2 credits per project")
print("- With 3 projects qualified: I could get 6+ credits")
