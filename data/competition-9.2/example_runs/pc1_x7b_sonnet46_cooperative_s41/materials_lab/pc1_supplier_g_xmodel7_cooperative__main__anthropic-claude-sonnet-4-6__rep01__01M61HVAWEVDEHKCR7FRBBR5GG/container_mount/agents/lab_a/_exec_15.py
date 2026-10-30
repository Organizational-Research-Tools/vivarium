
import pandas as pd
df = pd.read_csv('records.csv')

# Summarize what I have for the key prototypes
recipe_cols = ['base_sheet','secondary_sheet','binder_system','additive_package_1','additive_package_2',
               'additive_package_3','process_profile_1','process_profile_2','process_profile_3',
               'surface_treatment','joint_system','conditioning_step']

# Check p_21XPKFZDE5 (QP-4476)
mask = df['prototype_id'] == 'p_21XPKFZDE5'
if mask.any():
    row = df[mask].iloc[0]
    recipe = [row[c] if c in df.columns and pd.notna(row[c]) else '?' for c in recipe_cols]
    vals = df[mask]['value'].values
    print(f"p_21XPKFZDE5 (QP-4476): heat={vals.mean():.3f}°C, recipe={recipe}")

# Summary of where we stand
print("\n=== STATUS SUMMARY ===")
print("Rev B thresholds: heat≥78.25, strength≥7.19, water≥79.2")
print("\nTarget prototypes (P2G/3HW/8BB/57T/S2J/4PE/WB3/VA8/X9F/ZW3/DL8/3N8):")
for pid, proj in [('p_J6CX8AHRR3','QP-3473 PL-95'), ('p_S87ZV5EJH5','QP-7212 PL-95'),
                  ('p_YD1Q0XW9SA','QP-3089 PL-98'), ('p_21XPKFZDE5','QP-4476 PL-57')]:
    mask = df['prototype_id'] == pid
    if mask.any():
        heat_sub = df[mask & (df['test']=='seal hold temperature')]
        strength_sub = df[mask & (df['test']=='edge crush resistance')]
        water_sub = df[mask & (df['test']=='wet strength retained')]
        h_mean = heat_sub['value'].mean() if len(heat_sub)>0 else None
        s_mean = strength_sub['value'].mean() if len(strength_sub)>0 else None
        w_mean = water_sub['value'].mean() if len(water_sub)>0 else None
        h_str = f"{h_mean:.3f}°C {'✅' if h_mean and h_mean>=78.25 else '❌'}" if h_mean else "MISSING"
        s_str = f"{s_mean:.3f} {'✅' if s_mean and s_mean>=7.19 else '❌'}" if s_mean else "MISSING"
        w_str = f"{w_mean:.1f}% {'✅' if w_mean and w_mean>=79.2 else '❌'}" if w_mean else "MISSING"
        print(f"  {pid} ({proj}): heat={h_str}, strength={s_str}, water={w_str}")
    else:
        print(f"  {pid} ({proj}): no records")

# What records could I potentially cite for a submission?
print("\n=== Lab_e strength records I hold ===")
strength_records = df[(df['test']=='edge crush resistance') & (df['kind']=='panel')]
print(strength_records[['prototype_id','project','value','measured_by']].to_string())
