import pandas as pd
x=pd.read_csv('records.csv')
q=x[x.kind=='qualification'].groupby(['project','prototype_id','test']).agg(mean=('value','mean'),n=('value','count'),by=('measured_by','first')).reset_index()
p=q.pivot(index=['project','prototype_id'],columns='test',values='mean')
print('panels full candidates C > all:')
print(p[(p['seal hold temperature']>=78.625)&(p['edge crush resistance']>=7.235)&(p['wet strength retained']>=79.8)].to_string())
print('\nNear candidates existing qualification panels:')
for (pr,pid),row in p.iterrows():
    if (row['edge crush resistance']>=7.20 and row['wet strength retained']>=79.8) or (row['seal hold temperature']>=78.625 and row['wet strength retained']>=79.8): print(pr,pid,row.to_dict())
