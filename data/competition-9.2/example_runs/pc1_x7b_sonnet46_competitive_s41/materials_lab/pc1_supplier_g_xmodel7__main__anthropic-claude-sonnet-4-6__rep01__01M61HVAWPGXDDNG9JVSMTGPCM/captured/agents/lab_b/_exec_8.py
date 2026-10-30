
# Revision B thresholds
heat_thresh = 78.25   # was 77.5, +3 steps of 0.25
str_thresh  = 7.19    # was 7.10, +3 steps of 0.03
water_thresh = 79.2   # was 78.0, +3 steps of 0.4

print("=== REVISION B THRESHOLD ANALYSIS ===")
print(f"Heat:     ≥ {heat_thresh}°C")
print(f"Strength: ≥ {str_thresh} kN/m")
print(f"Water:    ≥ {water_thresh}%\n")

# QP-8265 p_KJZ5KNC3WG
h = 78.99875; s = 7.15985; w = 79.1980
print(f"QP-8265 p_KJZ5KNC3WG (submitted report):")
print(f"  Heat:     {h:.5f} {'✓' if h>=heat_thresh else '✗ FAIL'} (margin {(h-heat_thresh)/0.25:.2f} steps)")
print(f"  Strength: {s:.5f} {'✓' if s>=str_thresh  else '✗ FAIL'} (margin {(s-str_thresh)/0.03:.2f} steps)")
print(f"  Water:    {w:.4f}  {'✓' if w>=water_thresh else '✗ FAIL'} (margin {(w-water_thresh)/0.4:.2f} steps)")
print()

# Lab_a's p_4V8BTTYF7C QP-4476 (PL-57)
h2 = 78.19; s2 = 6.554; w2 = 80.70
print(f"QP-4476 p_4V8BTTYF7C (lab_a recipe):")
print(f"  Heat:     {h2:.2f} {'✓' if h2>=heat_thresh else '✗ FAIL'} (margin {(h2-heat_thresh)/0.25:.2f} steps)")
print(f"  Strength: {s2:.3f}  {'✓' if s2>=str_thresh  else '✗ FAIL'} (margin {(s2-str_thresh)/0.03:.2f} steps)")
print(f"  Water:    {w2:.2f}  {'✓' if w2>=water_thresh else '✗ FAIL'} (margin {(w2-water_thresh)/0.4:.2f} steps)")
print()

# Lab_e's H3F approach (QP-6843, old readings)
h3 = 74.5; s3 = 7.185; w3 = 78.97
print(f"Lab_e H3F approach (QP-6843, old readings):")
print(f"  Heat:     {h3:.1f}  {'✓' if h3>=heat_thresh else '✗ FAIL'} (margin {(h3-heat_thresh)/0.25:.2f} steps)")
print(f"  Strength: {s3:.3f}  {'✓' if s3>=str_thresh  else '✗ FAIL'} (margin {(s3-str_thresh)/0.03:.2f} steps)")
print(f"  Water:    {w3:.2f}  {'✓' if w3>=water_thresh else '✗ FAIL'} (margin {(w3-water_thresh)/0.4:.2f} steps)")
print()

# If pp1: WB3->4QB boosts strength +0.70 kN/m
s_new_8265 = s + 0.70
w_new_8265 = w  # pp1 not in water interactions
h_new_8265 = h  # pp1 not in heat interactions
print(f"QP-8265 p_KJZ5QA recipe with pp1=4QB (predicted):")
print(f"  Heat:     {h_new_8265:.5f} {'✓' if h_new_8265>=heat_thresh else '✗ FAIL'} (margin {(h_new_8265-heat_thresh)/0.25:.2f} steps)")
print(f"  Strength: {s_new_8265:.5f} {'✓' if s_new_8265>=str_thresh  else '✗ FAIL'} (margin {(s_new_8265-str_thresh)/0.03:.2f} steps)")
print(f"  Water:    {w_new_8265:.4f}  Water UNCERTAIN — same recipe ± noise")
print()

# If pp1 change also helps QP-4476
s_new_4476 = s2 + 0.70  # if 4QB boosts +0.70 for QP-4476 too
h_new_4476 = h2  # heat unchanged
w_new_4476 = w2
print(f"QP-4476 lab_a recipe with pp1=4QB (predicted):")
print(f"  Heat:     {h_new_4476:.2f} {'✓' if h_new_4476>=heat_thresh else '✗ FAIL'} (margin {(h_new_4476-heat_thresh)/0.25:.2f} steps)")
print(f"  Strength: {s_new_4476:.3f}  {'✓' if s_new_4476>=str_thresh  else '✗ FAIL'} (margin {(s_new_4476-str_thresh)/0.03:.2f} steps)")
print(f"  Water:    {w_new_4476:.2f}  {'✓' if w_new_4476>=water_thresh else '✗ FAIL'} (margin {(w_new_4476-water_thresh)/0.4:.2f} steps)")
print()
print("CONCLUSION: pp1=4QB on QP-4476 would pass STRENGTH and WATER but STILL FAILS HEAT (78.19 < 78.25)")
print("Need to also solve heat: must change a heat-interaction module (secondary/surface/binder or add_pkg3/pp3)")
print("Base×cond×joint (JA8×3N8×DL8) is locked in by water requirement")
print("Most dangerous change: surface_trt (7KL) — also in water interaction 7KL×M2P×2BR")
