import pandas as pd
r=pd.read_csv('records.csv'); p=r.groupby(['project','prototype_id','test']).agg(n=('value','count'),mean=('value','mean')).reset_index(); w=p.pivot(index=['project','prototype_id'],columns='test',values='mean').reset_index(); rec=r.drop_duplicates('prototype_id').set_index('prototype_id'); w=w.merge(rec[['base_sheet','secondary_sheet','binder_system','additive_package_1','additive_package_2','additive_package_3','process_profile_1','process_profile_2','process_profile_3','surface_treatment','joint_system','conditioning_step']],left_on='prototype_id',right_index=True,how='left');
H='seal hold temperature'; S='edge crush resistance'; W='wet strength retained';
for proj in sorted(w.project.unique()):
 x=w[(w.project==proj)&(w.base_sheet!='H8Z')].copy()
 x['shortfall']= (78.625-x[H]).clip(lower=0)/.25 + (7.235-x[S]).clip(lower=0)/.03 + (79.8-x[W]).clip(lower=0)/.4
 print('\n',proj)
 print(x.sort_values('shortfall').head(8)[['prototype_id',H,S,W,'shortfall','base_sheet','secondary_sheet','binder_system','additive_package_1','additive_package_2','additive_package_3','process_profile_1','process_profile_2','process_profile_3','surface_treatment','joint_system','conditioning_step']].to_string(index=False))