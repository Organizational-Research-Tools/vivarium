import pandas as pd
x=pd.read_csv('records.csv'); x['value']=pd.to_numeric(x.value)
q=x[x.kind=='qualification'].groupby(['project','prototype_id','instrument','test']).agg(mean=('value','mean'),n=('value','size')).reset_index()
p=q.pivot_table(index=['project','prototype_id'],columns='test',values='mean').reset_index()
rec=x.dropna(subset=['base_sheet']).groupby('prototype_id').first()[['base_sheet','secondary_sheet','binder_system','additive_package_1','additive_package_2','additive_package_3','process_profile_1','process_profile_2','process_profile_3','surface_treatment','joint_system','conditioning_step']]
p=p.join(rec,on='prototype_id')
h,s,w='seal hold temperature','edge crush resistance','wet strength retained'
print('full qualify')
print(p[(p[h]>=78.25)&(p[s]>=7.19)&(p[w]>=79.2)].to_string(index=False))
print('\nheat panels pass:')
print(p[p[h]>=78.25][['project','prototype_id',h,s,w,'base_sheet']].to_string(index=False))
expl=x[(x.kind=='exploratory')&(x.test=='seal hold temperature')].groupby(['project','prototype_id']).value.agg(['mean','count']).reset_index()
print('\nExploratory top heat')
print(expl.sort_values('mean',ascending=False).head(40).to_string(index=False))