import pandas as pd
D=pd.read_csv('records.csv')
mods=list(D.columns[11:])
P=D.groupby(['project','prototype_id','test'],as_index=False).agg(mean=('value','mean'),sd=('value','std'),n=('value','size'))
print('panels',len(P),'fingerprints',D.groupby('prototype_id')[mods].first().drop_duplicates().shape[0])
for pr,g in D.groupby('project'):
 print('\n',pr)
 print(g.groupby(['prototype_id','instrument','test'],as_index=False).agg(mean=('value','mean')).to_string(index=False))
print('\nidentical recipes across projects:')
R=D.groupby(['project','prototype_id'])[mods].first().reset_index()
for i,row in R.iterrows():
 for j,r2 in R.iloc[i+1:].iterrows():
  if all(row[mods]==r2[mods]): print(row.project,row.prototype_id,'=',r2.project,r2.prototype_id)
