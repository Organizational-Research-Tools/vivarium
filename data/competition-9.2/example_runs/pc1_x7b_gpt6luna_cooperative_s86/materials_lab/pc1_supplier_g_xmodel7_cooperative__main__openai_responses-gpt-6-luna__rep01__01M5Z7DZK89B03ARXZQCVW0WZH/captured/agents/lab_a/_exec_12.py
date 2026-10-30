import pandas as pd, numpy as np, random
from sklearn.preprocessing import OneHotEncoder
from sklearn.linear_model import Ridge
from sklearn.pipeline import make_pipeline
x=pd.read_csv('records.csv'); mods=['base_sheet','secondary_sheet','binder_system','additive_package_1','additive_package_2','additive_package_3','process_profile_1','process_profile_2','process_profile_3','surface_treatment','joint_system','conditioning_step']
intg=[['surface_treatment','process_profile_1','binder_system'],['additive_package_2','additive_package_3','surface_treatment'],['base_sheet','joint_system','process_profile_3'],['process_profile_1','additive_package_1','process_profile_3'],['additive_package_3','process_profile_2','additive_package_1'],['secondary_sheet','process_profile_3','additive_package_2']]
h=x[(x.test=='seal hold temperature') & x.base_sheet.notna()].groupby(['project','prototype_id']+mods).value.mean().reset_index()
def fe(df):
 z=df[['project']+mods].copy()
 for j,g in enumerate(intg): z['I'+str(j)]=df[g].astype(str).agg('|'.join,axis=1)
 return z
# variant options from lab_info
opts=[['8GP','SQ8','QG7'],['5AC','D5U','6TX','RK7'],['VQ6','T5L','YC8','P8G'],['S7U','57Y','QG6','7TW'],['74N','F8Y','EB7','K3K'],['XD8','7BD','P2E','4CW'],['9VQ','2A4','RZ8','H9M'],['QE8','9HJ','2JH','8KZ'],['3XM','E3W','79B','FJ2'],['96Y','T6A','UX3','L2J'],['62B','JE5','YX4','4ZD'],['SU2','6YN','84Z','YT2']]
base=['QG7','5AC','P8G','QG6','K3K','P2E','2A4','2JH','FJ2','UX3','YX4','YT2']
# use pools for differing alpha; offset based on known p_X
cands=[base.copy()]
# one factor
for i,op in enumerate(opts):
 for v in op:
  r=base.copy(); r[i]=v
  if r!=base:cands.append(r)
rng=np.random.default_rng(22)
for k in range(20000): cands.append([rng.choice(o) for o in opts])
C=pd.DataFrame(cands,columns=mods); C.insert(0,'project','QP-5174')
# predictions alpha 1,3,10,20 and corrected to exact p_X
outs=[]
for a in [1,3,10,20]:
 m=make_pipeline(OneHotEncoder(handle_unknown='ignore'),Ridge(alpha=a)).fit(fe(h),h.value)
 pred=m.predict(fe(C))
 p=pd.DataFrame([dict(project='QP-5174',**dict(zip(mods,base)))])
 bpred=m.predict(fe(p))[0]
 obs=71.5275
 outs.append(pred+(obs-bpred))
score=np.mean(outs,axis=0)
C['score']=score
C=C.drop_duplicates(mods).sort_values('score',ascending=False)
print('n',len(C)); print(C[['score']+mods].head(60).to_string(index=False))
print('onefactor'); print(C[C[mods].apply(lambda row: sum(row.values!=np.array(base)),axis=1)<=1][['score']+mods].head(40).to_string(index=False))
