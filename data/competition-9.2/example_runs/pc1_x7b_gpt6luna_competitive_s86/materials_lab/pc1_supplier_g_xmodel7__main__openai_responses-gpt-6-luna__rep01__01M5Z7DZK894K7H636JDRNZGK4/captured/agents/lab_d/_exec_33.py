import pandas as pd
x=pd.read_csv('records.csv')
print(x.shape)
print(x.kind.value_counts())
# unique prototype composition and panel means
mods=['base_sheet','secondary_sheet','binder_system','additive_package_1','additive_package_2','additive_package_3','process_profile_1','process_profile_2','process_profile_3','surface_treatment','joint_system','conditioning_step']
known=x.dropna(subset=mods).copy()
print('known prototypes',known.prototype_id.nunique())
g=known.groupby(['project','prototype_id','instrument']).agg(mean=('value','mean'),n=('value','size'),recipe=(mods[0], 'first'))
# aggregate per test panel
p=known.groupby(['project','prototype_id','instrument']).value.agg(['mean','count']).reset_index()
recipes=known.drop_duplicates('prototype_id').set_index('prototype_id')[mods]
p=p.join(recipes,on='prototype_id')
# recipes on projects with all tests panels
for proj in p.project.unique():
 q=p[p.project==proj]
 wide=q.pivot(index='prototype_id',columns='instrument',values='mean')
 full=wide.dropna()
 if len(full):
  out=full.copy(); out['weak']=pd.concat([(out.heat-78.25)/.25,(out.strength-7.19)/.03,(out.water-79.2)/.4],axis=1).min(axis=1)
  print('\n',proj, len(out))
  print(out.sort_values('weak',ascending=False).head(15).round(4).to_string())
# candidates known with one or two tests panel
print('\nrecent QP3617 p4 candidates')
q=p[p.project=='QP-3617'];print(q[['prototype_id','instrument','mean','count']].tail(80).to_string(index=False))