
import pandas as pd

# Analyze strength results
results = [
    ("p_GPA411RNAF", ["JA8", "3HW", "8BB", "5FE", "6FA", "L6C", "4QB", "P8G", "N7N", "ZW3", "9FU", "YV2"], 4.86782),
    ("p_9BDEFVD9DG", ["P2G", "3HW", "8BB", "5FE", "6FA", "L6C", "4QB", "P8G", "N7N", "ZW3", "9FU", "YV2"], 4.17029),
    ("p_9BDEFVD9DJ", ["DA9", "3HW", "8BB", "5FE", "6FA", "L6C", "4QB", "P8G", "N7N", "ZW3", "9FU", "YV2"], 4.91633),
    ("p_9BDEFVD9DM", ["U8H", "3HW", "8BB", "5FE", "6FA", "L6C", "4QB", "P8G", "N7N", "ZW3", "9FU", "YV2"], 3.59111),
    ("p_9BDEFVD9DP", ["JA8", "5BU", "8BB", "5FE", "6FA", "L6C", "4QB", "P8G", "N7N", "ZW3", "9FU", "YV2"], 4.88096),
    ("p_9BDEFVD9DR", ["JA8", "YX8", "8BB", "5FE", "6FA", "L6C", "4QB", "P8G", "N7N", "ZW3", "9FU", "YV2"], 4.90271),
    ("p_9BDEFVD9DT", ["JA8", "3HW", "M2P", "5FE", "6FA", "L6C", "4QB", "P8G", "N7N", "ZW3", "9FU", "YV2"], 5.47331),
    ("p_9BDEFVD9DW", ["JA8", "3HW", "NN7", "5FE", "6FA", "L6C", "4QB", "P8G", "N7N", "ZW3", "9FU", "YV2"], 5.53400),
    ("p_9BDEFVD9DY", ["JA8", "3HW", "T9M", "5FE", "6FA", "L6C", "4QB", "P8G", "N7N", "ZW3", "9FU", "YV2"], 4.96430),
    ("p_9BDEFVD9E0", ["JA8", "3HW", "8BB", "R5N", "6FA", "L6C", "4QB", "P8G", "N7N", "ZW3", "9FU", "YV2"], 4.93643),
    ("p_9BDEFVD9E2", ["JA8", "3HW", "8BB", "57T", "6FA", "L6C", "4QB", "P8G", "N7N", "ZW3", "9FU", "YV2"], 4.84919),
    ("p_9BDEFVD9E4", ["JA8", "3HW", "8BB", "QJ2", "6FA", "L6C", "4QB", "P8G", "N7N", "ZW3", "9FU", "YV2"], 4.82231),
    ("p_9BDEFVD9E6", ["JA8", "3HW", "8BB", "5FE", "B3P", "L6C", "4QB", "P8G", "N7N", "ZW3", "9FU", "YV2"], 6.30518),
    ("p_KYSDRKE51W", ["JA8", "3HW", "8BB", "5FE", "S2J", "L6C", "4QB", "P8G", "N7N", "ZW3", "9FU", "YV2"], 4.83800),
    ("p_KYSDRKE51Y", ["JA8", "3HW", "8BB", "5FE", "LD3", "L6C", "4QB", "P8G", "N7N", "ZW3", "9FU", "YV2"], 5.66627),
    ("p_KYSDRKE520", ["JA8", "3HW", "8BB", "5FE", "6FA", "4PE", "4QB", "P8G", "N7N", "ZW3", "9FU", "YV2"], 4.95476),
    ("p_KYSDRKE522", ["JA8", "3HW", "8BB", "5FE", "6FA", "QJ4", "4QB", "P8G", "N7N", "ZW3", "9FU", "YV2"], 4.23857),
    ("p_KYSDRKE524", ["JA8", "3HW", "8BB", "5FE", "6FA", "44B", "4QB", "P8G", "N7N", "ZW3", "9FU", "YV2"], 4.91837),
    ("p_KYSDRKE526", ["JA8", "3HW", "8BB", "5FE", "6FA", "L6C", "62D", "P8G", "N7N", "ZW3", "9FU", "YV2"], 5.59706),
    ("p_KYSDRKE528", ["JA8", "3HW", "8BB", "5FE", "6FA", "L6C", "UP5", "P8G", "N7N", "ZW3", "9FU", "YV2"], 5.60813),
    ("p_KYSDRKE52A", ["JA8", "3HW", "8BB", "5FE", "6FA", "L6C", "WB3", "P8G", "N7N", "ZW3", "9FU", "YV2"], 5.56583),
    ("p_KYSDRKE52C", ["JA8", "3HW", "8BB", "5FE", "6FA", "L6C", "4QB", "C5Q", "N7N", "ZW3", "9FU", "YV2"], 5.55590),
    ("p_KYSDRKE52E", ["JA8", "3HW", "8BB", "5FE", "6FA", "L6C", "4QB", "VA8", "N7N", "ZW3", "9FU", "YV2"], 4.86374),
    ("p_KYSDRKE52G", ["JA8", "3HW", "8BB", "5FE", "6FA", "L6C", "4QB", "2BR", "N7N", "ZW3", "9FU", "YV2"], 5.50526),
    ("p_KYSDRKE52J", ["JA8", "3HW", "8BB", "5FE", "6FA", "L6C", "4QB", "P8G", "X9F", "ZW3", "9FU", "YV2"], 4.94843),
    ("p_J3E23QHSRM", ["JA8", "3HW", "8BB", "5FE", "6FA", "L6C", "4QB", "P8G", "H3F", "ZW3", "9FU", "YV2"], 4.82039),
    ("p_J3E23QHSRP", ["JA8", "3HW", "8BB", "5FE", "6FA", "L6C", "4QB", "P8G", "N4L", "ZW3", "9FU", "YV2"], 4.13492),
    ("p_J3E23QHSRR", ["JA8", "3HW", "8BB", "5FE", "6FA", "L6C", "4QB", "P8G", "N7N", "5TZ", "9FU", "YV2"], 6.11054),
    ("p_J3E23QHSRT", ["JA8", "3HW", "8BB", "5FE", "6FA", "L6C", "4QB", "P8G", "N7N", "7KL", "9FU", "YV2"], 5.50673),
    ("p_J3E23QHSRW", ["JA8", "3HW", "8BB", "5FE", "6FA", "L6C", "4QB", "P8G", "N7N", "7TJ", "9FU", "YV2"], 5.54492),
    ("p_J3E23QHSRY", ["JA8", "3HW", "8BB", "5FE", "6FA", "L6C", "4QB", "P8G", "N7N", "ZW3", "57U", "YV2"], 4.26437),
    ("p_J3E23QHSS0", ["JA8", "3HW", "8BB", "5FE", "6FA", "L6C", "4QB", "P8G", "N7N", "ZW3", "DL8", "YV2"], 4.90790),
    ("p_J3E23QHSS2", ["JA8", "3HW", "8BB", "5FE", "6FA", "L6C", "4QB", "P8G", "N7N", "ZW3", "4GD", "YV2"], 4.23416),
    ("p_J3E23QHSS4", ["JA8", "3HW", "8BB", "5FE", "6FA", "L6C", "4QB", "P8G", "N7N", "ZW3", "9FU", "6JZ"], 4.82699),
    ("p_J3E23QHSS6", ["JA8", "3HW", "8BB", "5FE", "6FA", "L6C", "4QB", "P8G", "N7N", "ZW3", "9FU", "3N8"], 3.64748),
    ("p_J3E23QHSS8", ["JA8", "3HW", "8BB", "5FE", "6FA", "L6C", "4QB", "P8G", "N7N", "ZW3", "9FU", "G8Q"], 3.57482),
    ("p_J3E23QHSSA", ["U8H", "3HW", "NN7", "57T", "B3P", "QJ4", "WB3", "C5Q", "H3F", "ZW3", "4GD", "3N8"], 5.75096),
    ("p_96FTZ07JTK", ["JA8", "5BU", "M2P", "R5N", "B3P", "4PE", "62D", "C5Q", "X9F", "5TZ", "57U", "6JZ"], 5.78786),
    ("p_96FTZ07JTN", ["DA9", "3HW", "T9M", "QJ2", "LD3", "44B", "WB3", "2BR", "N4L", "7TJ", "4GD", "G8Q"], 5.05571),
    ("p_96FTZ07JTQ", ["P2G", "YX8", "NN7", "57T", "S2J", "QJ4", "UP5", "VA8", "H3F", "7KL", "DL8", "3N8"], 4.43852),
    ("p_96FTZ07JTS", ["U8H", "5BU", "8BB", "5FE", "6FA", "L6C", "4QB", "P8G", "N7N", "5TZ", "9FU", "YV2"], 5.42963),
    ("p_96FTZ07JTV", ["DA9", "YX8", "T9M", "QJ2", "LD3", "44B", "WB3", "2BR", "N4L", "7TJ", "57U", "G8Q"], 6.37355),
    ("p_96FTZ07JTX", ["P2G", "3HW", "M2P", "R5N", "S2J", "4PE", "62D", "VA8", "X9F", "ZW3", "DL8", "6JZ"], 6.37991),
    ("p_96FTZ07JTZ", ["JA8", "5BU", "NN7", "57T", "B3P", "QJ4", "WB3", "C5Q", "H3F", "7KL", "4GD", "3N8"], 6.37967),
    ("p_96FTZ07JV1", ["DA9", "3HW", "8BB", "R5N", "6FA", "QJ4", "UP5", "VA8", "X9F", "5TZ", "DL8", "6JZ"], 3.74429),
    ("p_96FTZ07JV3", ["P2G", "YX8", "T9M", "5FE", "S2J", "44B", "62D", "2BR", "N4L", "7TJ", "9FU", "3N8"], 4.90355),
    ("p_96FTZ07JV5", ["U8H", "3HW", "NN7", "QJ2", "LD3", "L6C", "WB3", "P8G", "H3F", "ZW3", "57U", "YV2"], 6.27659),
    ("p_96FTZ07JV7", ["JA8", "YX8", "NN7", "5FE", "S2J", "44B", "UP5", "2BR", "H3F", "7TJ", "DL8", "3N8"], 6.27107),
]

# Sort by strength
results_sorted = sorted(results, key=lambda x: x[2], reverse=True)
print(f"Strength threshold: 7.10 kN/m")
print(f"\nTop 15 results:")
for pid, recipe, val in results_sorted[:15]:
    above = val >= 7.10
    print(f"  {val:.4f} {'✓' if above else '✗'} {pid}: {recipe}")

print(f"\nBaseline value: {results[0][2]:.4f}")
print(f"\nModule effects (vs baseline {results[0][2]:.4f}):")
module_names = ["base_sheet", "secondary_sheet", "binder", "add_pkg1", "add_pkg2", "add_pkg3", "pp1", "pp2", "pp3", "surface_trt", "joint_sys", "cond_step"]
baseline_val = results[0][2]  # 4.86782
for i, (pid, recipe, val) in enumerate(results[1:36]):  # single-module changes
    effect = val - baseline_val
    print(f"  {module_names[i//3]} [{recipe[i//3]}]: {effect:+.4f} (raw: {val:.4f})")
