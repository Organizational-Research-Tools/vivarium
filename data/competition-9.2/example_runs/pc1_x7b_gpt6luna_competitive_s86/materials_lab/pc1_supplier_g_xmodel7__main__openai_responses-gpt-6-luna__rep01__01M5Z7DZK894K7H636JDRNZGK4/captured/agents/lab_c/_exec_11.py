import pandas as pd
x=pd.read_csv('records.csv')
w=x[(x.project=='QP-9219')&(x.test=='wet strength retained, %')&(x.kind=='exploratory')]
s=x[(x.project=='QP-9219')&(x.test=='edge crush resistance')&(x.kind=='exploratory')]
print('water n',len(w),'strength n',len(s))
print(w.sort_values('value',ascending=False)[['prototype_id','value','base_sheet','secondary_sheet','binder_system','additive_package_1','additive_package_2','additive_package_3','process_profile_1','process_profile_2','process_profile_3','surface_treatment','joint_system','conditioning_step']].to_string(index=False))
print('\nintersect top strength and water')
print(s.merge(w,on=['prototype_id','project'],suffixes=('_s','_w'))[['prototype_id','value_s','value_w']].sort_values('value_s',ascending=False).to_string(index=False))
print('\nA candidates rows')
print(x[x.prototype_id.isin(['p_MZ2MT0W3NX','p_ND59PQA2YG','p_ND59PQA2Y8','p_H508X1Y00R','p_ND59PQA2Y4','p_HQGXAP7GK7','p_ND59PQA2YC','p_MZ2MT0W3PS'])][['record_id','kind','test','value','prototype_id','base_sheet','secondary_sheet','binder_system','additive_package_1','additive_package_2','additive_package_3','surface_treatment']].to_string(index=False))