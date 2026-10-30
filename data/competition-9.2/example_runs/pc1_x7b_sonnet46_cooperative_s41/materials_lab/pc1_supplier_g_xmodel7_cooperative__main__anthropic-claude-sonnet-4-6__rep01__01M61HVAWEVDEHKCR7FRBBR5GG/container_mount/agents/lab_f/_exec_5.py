
import pandas as pd
pd.set_option('display.max_columns', None)
pd.set_option('display.width', 400)

df = pd.read_csv('records.csv')

modules = ['base_sheet', 'secondary_sheet', 'binder_system', 'additive_package_1', 
           'additive_package_2', 'additive_package_3', 'process_profile_1', 
           'process_profile_2', 'process_profile_3', 'surface_treatment', 
           'joint_system', 'conditioning_step']

# Group prototypes by recipe (same composition = same recipe family)
# Use the filing-status grouping from my_records: recipes grouped as (primary_id, alt1, alt2)
# Primary IDs for each recipe group (one per row in filing status):
# QP-3089: p_GR61XB2TYZ (GG7), p_1C3KSY7MJC
# QP-3473: p_KTBQ5A8DMJ, p_0TR8JD148X, p_FC7E87JJTT, p_ERK3YD03HP, p_1JB4S9JBGE, p_BW587HPKGR
# QP-4476: p_WWXN5W4HZR (GG7)
# QP-7212: p_4RVR94TWXD
# QP-8265: p_ZY10J8GD59, p_5HB53C74EQ

primary_ids = ['p_GR61XB2TYZ', 'p_1C3KSY7MJC',
               'p_KTBQ5A8DMJ', 'p_0TR8JD148X', 'p_FC7E87JJTT', 
               'p_ERK3YD03HP', 'p_1JB4S9JBGE', 'p_BW587HPKGR',
               'p_WWXN5W4HZR', 'p_4RVR94TWXD', 'p_ZY10J8GD59', 'p_5HB53C74EQ']

recipes = df[df['prototype_id'].isin(primary_ids)][['prototype_id', 'project'] + modules].drop_duplicates('prototype_id').set_index('prototype_id')

# Test results from my_records (the complete picture)
results = {
    'p_GR61XB2TYZ': {'proj': 'QP-3089', 'heat': 79.281, 'str': 7.254, 'water': 80.050, 'note': 'GG7!'},
    'p_1C3KSY7MJC': {'proj': 'QP-3089', 'heat': 78.220, 'str': 6.732, 'water': 79.152},
    'p_KTBQ5A8DMJ': {'proj': 'QP-3473', 'heat': 78.165, 'str': 7.150, 'water': 71.622},
    'p_0TR8JD148X': {'proj': 'QP-3473', 'heat': 78.645, 'str': 6.549, 'water': 79.832},
    'p_FC7E87JJTT': {'proj': 'QP-3473', 'heat': 73.137, 'str': 7.182, 'water': 80.298},
    'p_ERK3YD03HP': {'proj': 'QP-3473', 'heat': 78.529, 'str': 7.163, 'water': 72.994},
    'p_1JB4S9JBGE': {'proj': 'QP-3473', 'heat': 78.033, 'str': 7.224, 'water': 73.000},
    'p_BW587HPKGR': {'proj': 'QP-3473', 'heat': 78.120, 'str': 7.174, 'water': 73.140},
    'p_WWXN5W4HZR': {'proj': 'QP-4476', 'heat': None, 'str': None, 'water': 81.647, 'note': 'GG7!'},
    'p_4RVR94TWXD': {'proj': 'QP-7212', 'heat': 71.684, 'str': 6.603, 'water': 70.200},
    'p_ZY10J8GD59': {'proj': 'QP-8265', 'heat': 71.628, 'str': 6.468, 'water': 71.395},
    'p_5HB53C74EQ': {'proj': 'QP-8265', 'heat': 74.254, 'str': 7.203, 'water': 78.968},
}

print("=== DETAILED RECIPE ANALYSIS ===\n")
for pid in primary_ids:
    r = results[pid]
    rec = recipes.loc[pid] if pid in recipes.index else None
    note = r.get('note', '')
    h = r['heat']
    s = r['str']
    w = r['water']
    h_ok = '✓' if h and h>=77.5 else ('✗' if h else '?')
    s_ok = '✓' if s and s>=7.1 else ('✗' if s else '?')
    w_ok = '✓' if w and w>=78.0 else ('✗' if w else '?')
    print(f"{pid} [{r['proj']}] {note}")
    if rec is not None:
        print(f"  Recipe: {list(rec[modules])}")
    print(f"  Heat: {h:.3f}{h_ok}  Strength: {s:.4f}{s_ok}  Water: {w:.3f}{w_ok}")
    
    # Which tests fail?
    fails = []
    if h and h < 77.5: fails.append(f"heat needs +{(77.5-h)/0.25:.1f} steps")
    if s and s < 7.1: fails.append(f"strength needs +{(7.1-s)/0.03:.1f} steps")
    if w and w < 78.0: fails.append(f"water needs +{(78.0-w)/0.4:.1f} steps")
    if fails:
        print(f"  FAILS: {', '.join(fails)}")
    else:
        print(f"  ** PASSES ALL **")
    print()
