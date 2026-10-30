
# Verify lab_b's claimed margins for p_8E3MPG688H
thresholds = {'heat': 78.625, 'strength': 7.235, 'water': 79.800}
base_thresholds = {'heat': 78.625, 'strength': 7.235, 'water': 79.800}
steps = {'heat': 0.25, 'strength': 0.03, 'water': 0.4}

results = {'heat': 79.531, 'strength': 7.254, 'water': 80.850}

print("p_8E3MPG688H (QP-3473, GG7/8BB recipe) — Rev C margin analysis:")
margins = {}
for test in ['heat', 'strength', 'water']:
    margin_steps = (results[test] - base_thresholds[test]) / steps[test]
    margins[test] = margin_steps
    status = "✓" if results[test] >= thresholds[test] else "✗"
    print(f"  {test}: {results[test]} {status}  margin = {margin_steps:.2f} steps")

weakest = min(margins.values())
print(f"\n  Weakest margin: {weakest:.2f} steps")
print(f"  Rev C requirement (≥4.5 steps): {'PASSES' if weakest >= 4.5 else 'FAILS'}")
print()
print("This recipe WOULD HAVE QUALIFIED QP-3473 (PL-95) under Rev C.")
print()
print("KEY QUESTION: When did lab_b obtain all three panels for p_8E3MPG688H?")
print("If before the submission deadline, a QP-3473 report could have been filed.")
