import pandas as pd
df=pd.read_csv('records.csv')
mods=list(df.columns[11:23])
q=df[(df.kind=='qualification')&(df.project=='QP-1454')]
prot=df.drop_duplicates('prototype_id')[['prototype_id']+mods].set_index('prototype_id')
wm=q[q.test=='wet strength retained'].groupby('prototype_id')['value'].mean()
sm=q[q.test=='edge crush resistance'].groupby('prototype_id')['value'].mean()
hm=q[q.test=='seal hold temperature'].groupby('prototype_id')['value'].mean()
t=pd.concat([wm.rename('water'),sm.rename('str'),hm.rename('heat')],axis=1).join(prot)
print(t.to_string())