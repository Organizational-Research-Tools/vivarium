import pandas as pd, numpy as np
from sklearn.preprocessing import OneHotEncoder
from sklearn.compose import ColumnTransformer
from sklearn.linear_model import Ridge
from sklearn.pipeline import make_pipeline
x=pd.read_csv('records.csv'); s=x[x.test=='edge crush resistance'].groupby(['project','prototype_id'],as_index=False).value.mean()
cols=['base_sheet','secondary_sheet','binder_system','additive_package_1','additive_package_2','additive_package_3','process_profile_1','process_profile_2','process_profile_3','surface_treatment','joint_system','conditioning_step']
r=x.drop_duplicates(['project','prototype_id'])[['project','prototype_id']+cols]
d=s.merge(r,on=['project','prototype_id'])
ints=[['additive_package_1','binder_system','joint_system'],['additive_package_2','additive_package_3','surface_treatment'],['binder_system','process_profile_2','conditioning_step'],['process_profile_1','additive_package_1','process_profile_3'],['process_profile_1','additive_package_3','joint_system'],['secondary_sheet','process_profile_3','additive_package_2']]
for i,g in enumerate(ints): d['int'+str(i)]=d[g].astype(str).agg('|'.join,axis=1)
features=cols+['int'+str(i) for i in range(len(ints))]+['project']
# Target projection regularized for categories
enc=OneHotEncoder(handle_unknown='ignore')
model=make_pipeline(ColumnTransformer([('cat',enc,features)]),Ridge(alpha=10))
model.fit(d[features],d.value)
t=d[d.project=='QP-7092'].copy(); t['pred']=model.predict(t[features]); print('target observed/pred')
print(t[['prototype_id','value','pred']].to_string(index=False))
# random candidate generation evaluate model
variants=[['8GP','SQ8','QG7'],['5AC','D5U','6TX','RK7'],['VQ6','T5L','YC8','P8G'],['S7U','57Y','QG6','7TW'],['74N','F8Y','EB7','K3K'],['XD8','7BD','P2E','4CW'],['9VQ','2A4','RZ8','H9M'],['QE8','9HJ','2JH','8KZ'],['3XM','E3W','79B','FJ2'],['96Y','T6A','UX3','L2J'],['62B','JE5','YX4','4ZD'],['SU2','6YN','84Z','YT2']]
rng=np.random.default_rng(4); N=10000
cand=pd.DataFrame({c:rng.choice(v,len(candx)) for c,v,candx in []})
rows=[]
for j in range(N): rows.append([rng.choice(v) for v in variants])
c=pd.DataFrame(rows,columns=cols); c['project']='QP-7092'
for i,g in enumerate(ints): c['int'+str(i)]=c[g].astype(str).agg('|'.join,axis=1)
c['pred']=model.predict(c[features]); c=c.sort_values('pred',ascending=False)
print('\nBest candidates'); print(c[['pred']+cols].head(30).to_string(index=False))
print('\nBest known QP7092');print(t.sort_values('pred',ascending=False)[['prototype_id','value','pred']+cols].head(10).to_string(index=False))