
import pandas as pd
pd.set_option('display.max_columns', None)
pd.set_option('display.width', 400)

df = pd.read_csv('records.csv')

modules = ['base_sheet', 'secondary_sheet', 'binder_system', 'additive_package_1', 
           'additive_package_2', 'additive_package_3', 'process_profile_1', 
           'process_profile_2', 'process_profile_3', 'surface_treatment', 
           'joint_system', 'conditioning_step']

# Get unique recipe per prototype (using prototype with known composition)
recipes = df[df[modules[0]].notna()][['prototype_id', 'project'] + modules].drop_duplicates('prototype_id')

# The my_records groups: same recipe = same prototype "family"
# Let me group by composition to find unique recipes
recipes['recipe_key'] = recipes[modules].apply(tuple, axis=1)
unique_recipes = recipes.drop_duplicates('recipe_key').copy()

# Panel means per prototype
panel_df = df[df['kind'] == 'qualification']
means = panel_df.groupby(['prototype_id', 'test'])['value'].mean()

# Build per-recipe-key test results
recipe_results = {}
for _, row in unique_recipes.iterrows():
    rk = row['recipe_key']
    # Find all prototypes with this recipe
    same = recipes[recipes['recipe_key'] == rk]['prototype_id'].tolist()
    heat_vals = []
    strength_vals = []
    water_vals = []
    for pid in same:
        if pid in means.index:
            for test, val in means[pid].items():
                if 'temperature' in test or 'heat' in test.lower():
                    heat_vals.append(val)
                elif 'crush' in test or 'strength' in test.lower():
                    strength_vals.append(val)
                elif 'wet' in test or 'water' in test.lower():
                    water_vals.append(val)
    recipe_results[rk] = {
        'project': row['project'],
        'proto': row['prototype_id'],
        'heat': heat_vals[0] if heat_vals else None,
        'strength': strength_vals[0] if strength_vals else None,
        'water': water_vals[0] if water_vals else None,
        'gg7': row['secondary_sheet'] == 'GG7',
        'recipe': list(row[modules])
    }

print("=== UNIQUE RECIPES AND TEST RESULTS ===")
print(f"{'Proto':<20} {'Project':<10} {'Heat':>8} {'Str':>8} {'Water':>8} {'GG7':>5} | Recipe")
print("-"*150)
for rk, rd in sorted(recipe_results.items(), key=lambda x: x[1]['project']):
    h = f"{rd['heat']:.3f}" if rd['heat'] else "---"
    s = f"{rd['strength']:.4f}" if rd['strength'] else "---"
    w = f"{rd['water']:.3f}" if rd['water'] else "---"
    h_ok = '✓' if rd['heat'] and rd['heat'] >= 77.5 else ('✗' if rd['heat'] else '?')
    s_ok = '✓' if rd['strength'] and rd['strength'] >= 7.1 else ('✗' if rd['strength'] else '?')
    w_ok = '✓' if rd['water'] and rd['water'] >= 78.0 else ('✗' if rd['water'] else '?')
    passes = rd['heat'] and rd['strength'] and rd['water'] and rd['heat']>=77.5 and rd['strength']>=7.1 and rd['water']>=78.0
    flag = " *** PASS ***" if passes else ""
    gg7 = 'YES' if rd['gg7'] else 'no'
    print(f"{rd['proto']:<20} {rd['project']:<10} {h+h_ok:>9} {s+s_ok:>9} {w+w_ok:>9} {gg7:>5} | {rd['recipe']}{flag}")
