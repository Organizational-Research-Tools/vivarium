import pandas as pd
df=pd.read_csv('records.csv')
d=df[(df.project=='QP-4757')&(df.kind=='exploratory')&(df.measured_by=='lab_c')]
# group by module values vs water value
for col in ['base_sheet','secondary_sheet','binder_system','additive_package_1','additive_package_2','additive_package_3','process_profile_1','process_profile_2','process_profile_3','surface_treatment','joint_system','conditioning_step']:
    print(d.groupby(col).value.mean().round(2).to_string(),'\n')
# correlation with recipe of p_3TFNZHK1K7 which was best (~71)
best=d[d.prototype_id=='p_3TFNZHK1K7'].iloc[0]
print(best[[c for c in d.columns if c.endswith('sheet') or 'package' in c or 'profile' in c or 'treatment' in c or 'joint' in c or 'conditioning' in c]].to_string())