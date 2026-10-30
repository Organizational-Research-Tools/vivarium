
import pandas as pd
import numpy as np

df = pd.read_csv('records.csv')

recipe_cols = ['prototype_id', 'base_sheet', 'secondary_sheet', 'binder_system',
               'additive_package_1', 'additive_package_2', 'additive_package_3',
               'process_profile_1', 'process_profile_2', 'process_profile_3',
               'surface_treatment', 'joint_system', 'conditioning_step']

recipes = df[recipe_cols].dropna(subset=['base_sheet']).drop_duplicates('prototype_id')
recipes_dict = recipes.set_index('prototype_id').to_dict('index')

# Key prototypes from filing status:
key_protos = {
    'QP-4476_GG7_PASSES_ALL': 'p_PXAKTW39C3',   # GG7, passes all (banned)
    'QP-4476_str+water_pass': 'p_0TR8JD149R',   # heat fails  
    'QP-4476_str+water_pass2': 'p_PF0D437ZF5',  # heat fails
    'QP-4476_heat+water_pass': 'p_NP95G3B8R6',  # strength fails
    'QP-4476_heat+water_pass2': 'p_E0DS70E4AF', # strength fails
    'QP-6843_str+water_pass': 'p_ED8BM3M16K',   # heat fails
    'QP-7212_heat+str_pass': 'p_KTBQ5A8DND',    # water fails  
    'QP-3473_heat+str_pass': 'p_BPWVSBWDE3',    # water fails
    'QP-3473_GG7': 'p_8E3MPG688H',              # GG7, heat only
    'QP-3089_heat+str_pass': 'p_8ZZDCC8E8N',    # water fails
    'QP-8265_str+water_pass': 'p_EN88W8AJMM',   # heat fails
}

module_order = ['base_sheet', 'secondary_sheet', 'binder_system', 'additive_package_1',
                'additive_package_2', 'additive_package_3', 'process_profile_1', 
                'process_profile_2', 'process_profile_3', 'surface_treatment',
                'joint_system', 'conditioning_step']

print("NEAR-PASSING RECIPES WITH COMPOSITIONS:")
for label, pid in key_protos.items():
    if pid in recipes_dict:
        r = recipes_dict[pid]
        recipe = [r[m] for m in module_order]
        print(f"\n{label} ({pid}):")
        print(f"  {recipe}")
    else:
        print(f"\n{label} ({pid}): NO COMPOSITION DATA")

# Cross-reference: what's different between heat-good vs heat-bad recipes?
print("\n\n=== PATTERN ANALYSIS ===")
print("\nRecipes that PASS HEAT (from known compositions):")
print("p_PXAKTW39C3 (GG7): JA8, GG7, M2P, QJ2, 6FA, 44B, 62D, 2BR, N4L, 7KL, DL8, 3N8 → heat 78.78")
print("p_NP95G3B8R6:       ? → heat 78.37")
print("p_E0DS70E4AF:       ? → heat 78.34")
print("p_KTBQ5A8DND:       ? → heat 78.27")
print("p_8ZZDCC8E8N:       ? → heat 78.13")
print("p_BPWVSBWDE3:       ? → heat 78.07")
print("\nRecipes that FAIL HEAT:")
print("p_0TR8JD149R:       ? → heat 74.06")
print("p_PF0D437ZF5:       ? → heat 74.24")
print("p_ED8BM3M16K:       ? → heat 74.50")
print("p_EN88W8AJMM:       ? → heat 74.24")
