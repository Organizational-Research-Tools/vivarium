import pandas as pd
df=pd.read_csv('records.csv')
d=df[(df.project=='QP-4757')&(df.kind=='exploratory')&(df.measured_by=='lab_c')]
d=d.assign(v=d.value)
# compare L7A vs 7FT holding rest equal to WJ7/8KT/9AH best; 7FT appeared best in p_ZSMH9NWBS7
# check pair 7FT vs L7A with same modules
for proto,sub in d.groupby('prototype_id'):
    r=sub.iloc[0]
    print(r.prototype_id, r.base_sheet, r.secondary_sheet, r.binder_system, r.additive_package_1, r.additive_package_2, r.additive_package_3, r.process_profile_1, r.process_profile_2, r.process_profile_3, r.surface_treatment, r.joint_system, r.conditioning_step, round(sub.value.mean(),2))