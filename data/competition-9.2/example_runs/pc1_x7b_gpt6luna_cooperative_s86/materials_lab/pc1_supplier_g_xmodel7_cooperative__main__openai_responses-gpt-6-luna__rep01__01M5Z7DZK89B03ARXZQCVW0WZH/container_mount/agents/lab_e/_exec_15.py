import pandas as pd
x=pd.read_csv('records.csv')
d=x[x.project.eq('QP-9980')]
print(d.groupby(['prototype_id','test']).value.mean().unstack().to_string())