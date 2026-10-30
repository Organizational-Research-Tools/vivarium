
import pandas as pd
df = pd.read_csv('records.csv')

recipe_cols = ['base_sheet','secondary_sheet','binder_system','additive_package_1','additive_package_2',
               'additive_package_3','process_profile_1','process_profile_2','process_profile_3',
               'surface_treatment','joint_system','conditioning_step']

# Investigate QP-4476 heat-passing prototypes in detail
passing_ids = ['p_CRCFHBNN4T','p_E0DS70E4AF','p_E0DS70E4B1','p_HVKTAHESX4',
               'p_NP95G3B8R6','p_PXAKTW39C3','p_QVA9FKHJ9N','p_WWXN5W4HZR']

print("=== QP-4476 prototypes with heat >= 78.25°C ===")
for pid in passing_ids:
    mask = df['prototype_id'] == pid
    if mask.any():
        row = df[mask].iloc[0]
        vals = df[mask]['value'].values
        recipe = {c: row.get(c, '?') for c in recipe_cols}
        print(f"\n{pid}: heat={vals.mean():.3f}°C (n={len(vals)})")
        print(f"  base={recipe['base_sheet']}, sec={recipe['secondary_sheet']}, binder={recipe['binder_system']}")
        print(f"  ap1={recipe['additive_package_1']}, ap2={recipe['additive_package_2']}, ap3={recipe['additive_package_3']}")
        print(f"  pp1={recipe['process_profile_1']}, pp2={recipe['process_profile_2']}, pp3={recipe['process_profile_3']}")
        print(f"  surf={recipe['surface_treatment']}, joint={recipe['joint_system']}, cond={recipe['conditioning_step']}")
        gg7_flag = 'GG7' if recipe['secondary_sheet']=='GG7' else 'no-GG7'
        print(f"  Status: {gg7_flag}")
    else:
        print(f"{pid}: no recipe data (composition unknown)")

# Also check p_D8ZWGXFHRW (QP-6843)
print("\n=== QP-6843 heat-passing prototype ===")
mask = df['prototype_id'] == 'p_D8ZWGXFHRW'
if mask.any():
    row = df[mask].iloc[0]
    vals = df[mask]['value'].values
    recipe = {c: row.get(c, '?') for c in recipe_cols}
    print(f"p_D8ZWGXFHRW: heat={vals.mean():.3f}°C")
    print(f"  {[recipe[c] for c in recipe_cols]}")
else:
    print("p_D8ZWGXFHRW: no recipe data")

# Check all records for those IDs — some might have been measured elsewhere
print("\n=== All records for promising prototypes ===")
for pid in passing_ids + ['p_D8ZWGXFHRW']:
    sub = df[df['prototype_id']==pid]
    print(f"{pid}: {len(sub)} records across instruments: {sub['instrument'].unique() if 'instrument' in sub.columns else sub['test'].unique()}")
