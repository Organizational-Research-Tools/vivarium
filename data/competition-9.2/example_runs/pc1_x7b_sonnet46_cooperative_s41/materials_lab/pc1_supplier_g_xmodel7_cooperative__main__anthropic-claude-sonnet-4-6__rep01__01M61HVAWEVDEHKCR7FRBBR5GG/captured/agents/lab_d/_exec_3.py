
import pandas as pd

# Thresholds
HEAT_THRESH = 77.5   # °C
STR_THRESH  = 7.1    # kN/m
WATER_THRESH = 78.0  # %

# Steps
HEAT_STEP   = 0.25
STR_STEP    = 0.03
WATER_STEP  = 0.4

modules = ['base_sheet','secondary_sheet','binder_system','additive_package_1',
           'additive_package_2','additive_package_3','process_profile_1',
           'process_profile_2','process_profile_3','surface_treatment',
           'joint_system','conditioning_step']

df = pd.read_csv('records.csv')

# Get panel means per prototype per test
panels = df[df['kind']=='qualification'].groupby(
    ['project','prototype_id','test'])['value'].mean().unstack('test')
panels.columns.name = None
panels = panels.rename(columns={
    'seal hold temperature':'heat',
    'edge crush resistance':'strength',
    'wet strength retained':'water'})

# Add pass/fail
for col, thr in [('heat',HEAT_THRESH),('strength',STR_THRESH),('water',WATER_THRESH)]:
    if col in panels.columns:
        panels[col+'_pass'] = panels[col] >= thr

# Get compositions
comps = (df.dropna(subset=['base_sheet'])
           .drop_duplicates('prototype_id')[['prototype_id','project']+modules]
           .set_index('prototype_id'))

# Join compositions
summary = panels.join(comps[modules], how='left')
summary['GG7'] = summary['secondary_sheet'] == 'GG7'

# Overall status
print("=== KEY RECIPE: p_PXAKTW39C3 (GG7) ===")
star = summary.loc[summary.index.get_level_values('prototype_id') == 'p_PXAKTW39C3']
print(star[['heat','strength','water','heat_pass','strength_pass','water_pass','GG7']].to_string())
print()

print("=== GG7 NOTE: adds ~2 steps to each test ===")
print(f"  Heat: +{2*HEAT_STEP} °C | Strength: +{2*STR_STEP} kN/m | Water: +{2*WATER_STEP} %")
print()
print("GG7 recipe (p_PXAKTW39C3) expected WITHOUT GG7:")
print(f"  heat:     {78.77925 - 2*HEAT_STEP:.3f} °C  (thresh {HEAT_THRESH}) -> PASS" 
      if 78.77925 - 2*HEAT_STEP >= HEAT_THRESH else "FAIL")
print(f"  strength: {7.25351  - 2*STR_STEP:.5f} kN/m (thresh {STR_THRESH}) -> PASS"
      if 7.25351 - 2*STR_STEP >= STR_THRESH else "FAIL")
print(f"  water:    {81.6468  - 2*WATER_STEP:.4f} %    (thresh {WATER_THRESH}) -> PASS"
      if 81.6468 - 2*WATER_STEP >= WATER_THRESH else "FAIL")
print()

print("=== PL-95 WATER PROBLEM: QP-7212 and QP-3473 ===")
print("Water interaction: AP2 × joint system × AP3")
print("QP-7212: LD3 × 9FU × 4PE -> water=73.46% (FAIL by", round((78.0-73.46)/0.4,1), "steps)")
print("QP-3473: LD3 × DL8 × L6C -> water=73.07% (FAIL by", round((78.0-73.07)/0.4,1), "steps)")
print("QP-3089 GOOD: B3P × DL8 × 44B -> water=79.14% (PASS)")
print("QP-4476 GOOD (GG7 adj): 6FA × DL8 × 44B -> water~80.85% (PASS)")
print()
print("=== PL-98 STRENGTH PROBLEM: QP-3089 ===")
print("Recipe DA9/3HW/NN7/QJ2/B3P/44B... -> strength=6.73 (FAIL by", round((7.1-6.73)/0.03,1), "steps)")
print("GG7 recipe composition uses JA8/GG7/M2P -> strength=7.25")
print("Without GG7: expected 7.19 kN/m (PASS)")
