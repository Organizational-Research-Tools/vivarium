import pandas as pd
x=pd.read_csv('records.csv')
q=x[x.project.eq('QP-6879')]
print(q.groupby(['prototype_id','test','kind']).value.agg(['count','mean']).unstack(['test','kind']).to_string(max_rows=100))