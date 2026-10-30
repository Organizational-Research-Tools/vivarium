import pandas as pd
x=pd.read_csv('records.csv'); q=x[x.project=='QP-3617']
print(q.groupby(['prototype_id','test','kind','measured_by']).value.agg(['count','mean']).to_string())