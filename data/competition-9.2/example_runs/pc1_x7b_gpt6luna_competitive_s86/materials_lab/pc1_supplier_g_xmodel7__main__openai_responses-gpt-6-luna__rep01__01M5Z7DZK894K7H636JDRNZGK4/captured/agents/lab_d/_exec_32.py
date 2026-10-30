import pandas as pd
r=pd.read_csv('records.csv')
q=r[r.project=='QP-3617'].copy()
cols=['base_sheet','secondary_sheet','binder_system','additive_package_1','additive_package_2','additive_package_3','process_profile_1','process_profile_2','process_profile_3','surface_treatment','joint_system','conditioning_step']
# numeric mean by prototype/test/kind; one exploratory reading or 6 panel
s=q.groupby(['prototype_id','test','kind','measured_by']).value.agg(['mean','count']).reset_index()
wide=s.pivot_table(index='prototype_id',columns='test',values='mean',aggfunc='first')
comp=q.groupby('prototype_id')[cols].first()
out=comp.join(wide).join(q.groupby('prototype_id').project.first())
print(out[['base_sheet']+list(wide.columns)].dropna(subset=['base_sheet']).to_string())