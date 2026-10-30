import pandas as pd
df=pd.read_csv('records.csv')
q=df[df['kind']=='qualification']
g=q.groupby(['project','prototype_id','test'])['value'].mean().unstack()
print(g.to_string())
