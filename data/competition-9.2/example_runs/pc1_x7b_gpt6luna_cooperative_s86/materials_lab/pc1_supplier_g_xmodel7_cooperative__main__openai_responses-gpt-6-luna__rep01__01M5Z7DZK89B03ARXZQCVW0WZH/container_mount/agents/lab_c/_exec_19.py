import pandas as pd
x=pd.read_csv('records.csv')
y=x[x.project.eq('QP-3617')]
print('rows',len(y),'prototypes',y.prototype_id.nunique())
print(y.groupby(['prototype_id','test']).agg(n=('value','size'),mean=('value','mean'),by=('measured_by','first')).to_string())
print('\nrecipes')
for p,g in y.groupby('prototype_id'):
 print(p, g.iloc[0][['base_sheet','secondary_sheet','binder_system','additive_package_1','additive_package_2','additive_package_3','process_profile_1','process_profile_2','process_profile_3','surface_treatment','joint_system','conditioning_step']].tolist())