
import pandas as pd
df = pd.read_csv('records.csv')
print("Columns:", list(df.columns))
print()

# Look at strength records
strength = df[df['instrument']=='strength'].copy()
print(f"Total strength records: {len(strength)}")

# Show unique prototypes with strength data, mean per prototype
if len(strength) > 0:
    agg = strength.groupby(['project','prototype_id'])['value'].agg(['mean','count']).reset_index()
    agg.columns = ['project','prototype_id','strength_mean','n']
    agg['margin_steps'] = (agg['strength_mean'] - 7.1) / 0.03
    agg['pass_revC'] = agg['strength_mean'] >= 7.235
    print(agg.sort_values('strength_mean', ascending=False).to_string())

print()
# Water records relevant to PL-95, PL-98 projects
water = df[df['instrument']=='water'].copy()
water_agg = water.groupby(['project','prototype_id'])['value'].agg(['mean','count']).reset_index()
water_agg.columns = ['project','prototype_id','water_mean','n']
water_agg['margin_steps'] = (water_agg['water_mean'] - 78.0) / 0.4
water_agg['pass_revC'] = water_agg['water_mean'] >= 79.8
print("Water records by prototype:")
print(water_agg.sort_values('water_mean', ascending=False).to_string())
