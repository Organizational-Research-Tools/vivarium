import pandas as pd
x=pd.read_csv('records.csv')
w=x[(x.project=='QP-9219')&(x.test=='wet strength retained')&(x.kind=='exploratory')][['prototype_id','value']].rename(columns={'value':'water'})
s=x[(x.project=='QP-9219')&(x.test=='edge crush resistance')&(x.kind=='exploratory')][['prototype_id','value']].rename(columns={'value':'strength'})
c=x[(x.project=='QP-9219')&(x.kind=='exploratory')].drop_duplicates('prototype_id')[['prototype_id','base_sheet','secondary_sheet','binder_system','additive_package_1','additive_package_2','additive_package_3','process_profile_1','process_profile_2','process_profile_3','surface_treatment','joint_system','conditioning_step']]
d=s.merge(w,on='prototype_id').merge(c,on='prototype_id').sort_values('strength',ascending=False)
print(d.head(15).to_string(index=False))