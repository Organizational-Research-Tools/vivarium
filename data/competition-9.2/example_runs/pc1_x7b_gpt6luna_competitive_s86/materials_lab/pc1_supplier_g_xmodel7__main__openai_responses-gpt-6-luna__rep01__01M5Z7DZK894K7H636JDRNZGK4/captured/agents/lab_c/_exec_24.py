import pandas as pd
x=pd.read_csv('records.csv'); q=x[x.project.eq('QP-3617')]
cols=['base_sheet','secondary_sheet','binder_system','additive_package_1','additive_package_2','additive_package_3','process_profile_1','process_profile_2','process_profile_3','surface_treatment','joint_system','conditioning_step']
# show prototypes having records with water exploratory >79.2 with recipe
w=q[(q.test=='wet strength retained')&(q.kind=='exploratory')]
print('water screens >79.2',len(w[w.value>=79.2]))
print(w[w.value>=79.2][['prototype_id','value']+cols].to_string(index=False))
print('\nAll prototypes and measured tests')
print(q.groupby(['prototype_id','test','kind']).value.agg(['size','mean']).to_string())