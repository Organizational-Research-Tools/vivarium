import pandas as pd
df=pd.read_csv('records.csv')
mods=list(df.columns[11:23])
prot=df.drop_duplicates('prototype_id')[['project','prototype_id']+mods]
want=['p_HNJG4Q0WFM','p_A6QG873ZCR','p_SMN29C0NWH','p_9RQ03FNFG8','p_NSPXY0VY7J','p_CY9YNQA9DM','p_C4WKEC66VP','p_YYDVBJM1P1']
print(prot[prot.prototype_id.isin(want)].to_string())
# water means of recipes with RQ5 surface
q=df[df.kind=='qualification']
wm=q[(q.test=='wet strength retained')].merge(prot,on='prototype_id')
print(wm[wm.surface_treatment=='RQ5'][['prototype_id','value']].groupby('prototype_id')['value'].mean().to_string())