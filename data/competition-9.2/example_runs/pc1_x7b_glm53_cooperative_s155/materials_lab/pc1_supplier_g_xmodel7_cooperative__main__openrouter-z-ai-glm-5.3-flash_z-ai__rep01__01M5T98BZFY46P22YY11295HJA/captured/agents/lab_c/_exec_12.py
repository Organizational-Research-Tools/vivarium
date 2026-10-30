import pandas as pd
df=pd.read_csv('records.csv')
mods=list(df.columns[11:23])
prot=df.drop_duplicates('prototype_id')[['project','prototype_id']+mods]
q=df[df.kind=='qualification']
wm=q[(q.test=='wet strength retained')].merge(prot,left_on='prototype_id',right_on='prototype_id',suffixes=('','_y'))
print(wm[wm.surface_treatment=='RQ5'][['prototype_id','project','value']].groupby(['project','prototype_id'])['value'].agg(['mean','count']).to_string())
print()
print(wm[wm.base_sheet=='3F4'][['prototype_id','project','value']].groupby(['project','prototype_id'])['value'].mean().to_string())