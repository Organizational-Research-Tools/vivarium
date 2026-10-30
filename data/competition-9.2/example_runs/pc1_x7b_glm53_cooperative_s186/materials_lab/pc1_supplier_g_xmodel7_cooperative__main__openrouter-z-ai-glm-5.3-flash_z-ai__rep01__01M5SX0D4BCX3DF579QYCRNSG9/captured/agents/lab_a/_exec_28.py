import pandas as pd
d=pd.read_csv('records.csv')
q=d[(d.kind!='exploratory')|True]
g=d.groupby(['project','prototype_id','test']).value.agg(['count','mean']).round(3)
# best recipe-level: compute per prototype per test mean, then see prototypes with high heat & strength & water
p=d.groupby(['project','prototype_id','test']).value.mean().unstack()
p['min']=p.min(axis=1)
print(p.sort_values('min',ascending=False).head(25).round(3).to_string())