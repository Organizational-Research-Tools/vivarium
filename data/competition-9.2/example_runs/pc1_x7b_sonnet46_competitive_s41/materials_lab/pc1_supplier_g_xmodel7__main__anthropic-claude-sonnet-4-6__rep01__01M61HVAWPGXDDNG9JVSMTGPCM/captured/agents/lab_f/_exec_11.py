
# Map out credit scenarios for program success
print("=== PATH TO 3-LAB SUCCESS ===")
print()
print("Step 1: QP-4476 accepted (lab_a submits, lab_b strength, lab_f water, lab_a heat)")
print("  lab_e: 6, lab_f: 4, lab_d: 3, lab_a: 2, lab_b: 1")
print("  -> lab_e and lab_f succeed (>=4). Need ONE more lab to reach 4.")
print()
print("Step 2: QP-8265 accepted (lab_b submits, lab_d heat, lab_f water, lab_b strength)")
print("  lab_d: 3+1=4  <- critical!")
print("  lab_f: 4+1=5  <- bonus")
print("  lab_b: 1+2=3")
print("  Final: lab_e 6, lab_f 5, lab_d 4 -> ALL THREE >= 4 -> PROGRAM SUCCESS!")
print()
print("KEY: lab_d must measure heat on p_KJZ5KNC3WG (QP-8265, lab_b prototype)")
print("     This gives lab_d the 4th credit needed.")
print()
print("=== WATER records for QP-8265 (p_KJZ5KNC3WG) ready for lab_b to cite ===")
water_ids = ['r_DTHTFTYJK9','r_DTHTFTYJKA','r_DTHTFTYJKB',
             'r_DTHTFTYJKC','r_DTHTFTYJKD','r_DTHTFTYJKE']
values = [79.5720, 79.4548, 78.8336, 78.9728, 79.0252, 79.3296]
import numpy as np
print(f"Records: {water_ids}")
print(f"Mean: {np.mean(values):.4f}% (threshold 78.0%) -> margin {(np.mean(values)-78.0)/0.4:.2f} steps")
