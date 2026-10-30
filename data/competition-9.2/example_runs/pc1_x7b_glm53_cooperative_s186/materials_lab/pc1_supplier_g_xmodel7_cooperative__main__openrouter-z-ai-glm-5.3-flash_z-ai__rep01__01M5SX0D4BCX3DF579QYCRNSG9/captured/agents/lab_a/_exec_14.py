import pandas as pd
df = pd.read_csv('records.csv')
h = df[(df.project=='QP-8476') & (df.test=='seal hold temperature')]
tn6 = h[h.secondary_sheet=='TN6'].sort_values('value', ascending=False)
cols=['prototype_id','value','additive_package_1','additive_package_2','additive_package_3','process_profile_1','process_profile_2','process_profile_3','surface_treatment','joint_system','conditioning_step']
print(tn6[cols].head(20).to_string())
print('\n--- 2CK/2CS add3 heat:')
sub = h[h.additive_package_2.isin(['2CK','2CS'])].sort_values('value',ascending=False)
print(sub[cols+['secondary_sheet']].head(12).to_string())
print('\n--- top heat overall QP-8476:')
print(h.sort_values('value',ascending=False)[['prototype_id','value','secondary_sheet','additive_package_2','conditioning_step']].head(12).to_string())