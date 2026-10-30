import pandas as pd
x=pd.read_csv('records.csv')
q=x[x.project=='QP-6879']
print(q.groupby(['prototype_id','instrument','kind','measured_by']).value.agg(['count','mean']).to_string())