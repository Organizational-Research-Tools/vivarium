
import pandas as pd

df = pd.read_csv('records.csv')
modules = ['base_sheet', 'secondary_sheet', 'binder_system', 'additive_package_1', 
           'additive_package_2', 'additive_package_3', 'process_profile_1', 
           'process_profile_2', 'process_profile_3', 'surface_treatment', 
           'joint_system', 'conditioning_step']

# Print full recipe table for existing data with color-coded results
print("=== PATTERN ANALYSIS FOR WATER ===\n")
print("Focus: Why do some QP-3473 recipes get good water (>78%) and others get bad water?")
print()

# Get composition for each primary prototype
primary_data = {
    'p_0TR8JD148X': {'proj': 'QP-3473', 'heat': 78.645, 'str': 6.549, 'water': 79.832, 'verdict': 'GOOD water, BAD strength'},
    'p_FC7E87JJTT': {'proj': 'QP-3473', 'heat': 73.137, 'str': 7.182, 'water': 80.298, 'verdict': 'GOOD water, BAD heat'},
    'p_ERK3YD03HP': {'proj': 'QP-3473', 'heat': 78.529, 'str': 7.163, 'water': 72.994, 'verdict': 'BAD water'},
    'p_1JB4S9JBGE': {'proj': 'QP-3473', 'heat': 78.033, 'str': 7.224, 'water': 73.000, 'verdict': 'BAD water'},
    'p_BW587HPKGR': {'proj': 'QP-3473', 'heat': 78.120, 'str': 7.174, 'water': 73.140, 'verdict': 'BAD water'},
    'p_KTBQ5A8DMJ': {'proj': 'QP-3473', 'heat': 78.165, 'str': 7.150, 'water': 71.622, 'verdict': 'BAD water'},
}

primary_ids = list(primary_data.keys())
recs = df[df['prototype_id'].isin(primary_ids)][['prototype_id']+modules].drop_duplicates('prototype_id').set_index('prototype_id')

# Compare module-by-module
print(f"{'Module':<20} | {'0TR(W+)':>10} {'FC7(W+)':>10} | {'ERK(W-)':>10} {'1JB(W-)':>10} {'BW5(W-)':>10} {'KTB(W-)':>10}")
print("-"*100)
for m in modules:
    vals = {pid: recs.loc[pid, m] if pid in recs.index else '?' for pid in primary_ids}
    good_water_vals = [vals['p_0TR8JD148X'], vals['p_FC7E87JJTT']]
    bad_water_vals = [vals['p_ERK3YD03HP'], vals['p_1JB4S9JBGE'], vals['p_BW587HPKGR'], vals['p_KTBQ5A8DMJ']]
    
    # Is there a pattern?
    marker = ""
    if len(set(good_water_vals)) == 1 and good_water_vals[0] not in bad_water_vals:
        marker = " *** DIFFERENTIATOR"
    elif good_water_vals[0] == good_water_vals[1] and good_water_vals[0] not in bad_water_vals:
        marker = " *** CONSISTENT"
        
    print(f"{m:<20} | {vals['p_0TR8JD148X']:>10} {vals['p_FC7E87JJTT']:>10} | {vals['p_ERK3YD03HP']:>10} {vals['p_1JB4S9JBGE']:>10} {vals['p_BW587HPKGR']:>10} {vals['p_KTBQ5A8DMJ']:>10}{marker}")

print()
print("=== WATER INTERACTION MODULES ===")
print("additive_package_2 × joint_system × additive_package_3: affects water")
print("additive_package_3 × base_sheet × process_profile_3: affects heat, strength, water")
print("conditioning_step × process_profile_3 × additive_package_1: affects water")
print("surface_treatment × binder_system × process_profile_2: affects heat, strength, water")
print("process_profile_3 × binder_system × base_sheet: affects water")
