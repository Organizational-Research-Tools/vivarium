import pandas as pd
x=pd.read_csv('records.csv');
mods=[c for c in x if c in ['base_sheet','secondary_sheet','binder_system','additive_package_1','additive_package_2','additive_package_3','process_profile_1','process_profile_2','process_profile_3','surface_treatment','joint_system','conditioning_step']]
g=x.groupby(['project','prototype_id','test']).agg(mean=('value','mean'),n=('value','size'),measured=('measured_by','first')).reset_index()
w=g.pivot(index=['project','prototype_id'],columns='test',values='mean').reset_index()
meta=x.groupby(['project','prototype_id'])[mods].first().reset_index(); z=w.merge(meta,on=['project','prototype_id']);
print('prototypes',len(z)); print(z.to_string(index=False))