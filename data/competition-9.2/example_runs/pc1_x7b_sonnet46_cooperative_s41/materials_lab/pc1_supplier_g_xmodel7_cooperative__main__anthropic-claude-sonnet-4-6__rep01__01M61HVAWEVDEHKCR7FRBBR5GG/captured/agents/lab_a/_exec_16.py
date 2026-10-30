
import pandas as pd
df = pd.read_csv('records.csv')

# Check QP-6843 fully
sub = df[df['project']=='QP-6843']
print("=== QP-6843 records ===")
for pid, grp in sub.groupby('prototype_id'):
    tests = {}
    for test, tg in grp.groupby('test'):
        tests[test] = (tg['value'].mean(), len(tg[tg['kind']=='qualification']), tg['value'].values.tolist())
    recipe_row = grp.iloc[0]
    recipe_cols = ['base_sheet','secondary_sheet','binder_system','additive_package_1','additive_package_2',
                   'additive_package_3','process_profile_1','process_profile_2','process_profile_3',
                   'surface_treatment','joint_system','conditioning_step']
    recipe = [recipe_row.get(c,'?') for c in recipe_cols]
    print(f"\n{pid}: {recipe}")
    for test, (mean, n_qual, vals) in tests.items():
        thresh = {'seal hold temperature': 78.25, 'edge crush resistance': 7.19, 'wet strength retained': 79.2}
        t = thresh.get(test, 0)
        status = '✅' if mean >= t else '❌'
        print(f"  {test}: mean={mean:.3f}, n_qual={n_qual} {status}")

# Also check QP-4476 for any non-GG7 recipe with all three passing
print("\n=== QP-4476 non-GG7 complete recipes ===")
sub4 = df[df['project']=='QP-4476']
for pid, grp in sub4.groupby('prototype_id'):
    if grp.iloc[0].get('secondary_sheet') == 'GG7':
        continue
    tests = {}
    for test, tg in grp.groupby('test'):
        if len(tg[tg['kind']=='qualification']) >= 6:
            tests[test] = tg['value'].mean()
    if len(tests) == 3:
        h = tests.get('seal hold temperature', 0)
        s = tests.get('edge crush resistance', 0)
        w = tests.get('wet strength retained', 0)
        all_pass = h>=78.25 and s>=7.19 and w>=79.2
        print(f"  {pid}: heat={h:.3f}, str={s:.3f}, water={w:.3f} -> {'ALL PASS!' if all_pass else 'FAILS'}")
        recipe_row = grp.iloc[0]
        recipe_cols = ['base_sheet','secondary_sheet','binder_system','additive_package_1','additive_package_2',
                       'additive_package_3','process_profile_1','process_profile_2','process_profile_3',
                       'surface_treatment','joint_system','conditioning_step']
        recipe = [recipe_row.get(c,'?') for c in recipe_cols]
        print(f"    recipe: {recipe}")
