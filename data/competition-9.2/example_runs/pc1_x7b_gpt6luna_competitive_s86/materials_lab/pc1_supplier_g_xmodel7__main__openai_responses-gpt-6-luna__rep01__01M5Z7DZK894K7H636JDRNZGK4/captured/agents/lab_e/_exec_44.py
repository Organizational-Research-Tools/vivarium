import pandas as pd
x=pd.read_csv('records.csv')
for project in x.project.dropna().unique():
 y=x[(x.project==project)&(x.instrument=='strength')]
 if not len(y):continue
 m=y[y.kind=='qualification'].groupby('prototype_id').value.agg(['count','mean'])
 print('\n',project)
 print(m[(m['count']==6)&(m['mean']>=7.20)].sort_values('mean',ascending=False).head(30).to_string())
