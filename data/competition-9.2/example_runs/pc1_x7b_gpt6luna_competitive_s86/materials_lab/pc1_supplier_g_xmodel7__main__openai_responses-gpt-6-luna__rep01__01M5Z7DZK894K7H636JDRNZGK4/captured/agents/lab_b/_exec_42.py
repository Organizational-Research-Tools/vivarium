import pandas as pd
x=pd.read_csv('records.csv')
ids=['p_SVR5NZMYFM','p_9BPKMPQZK5','p_NBE0SSEEDQ']
q=x[x.prototype_id.isin(ids)]
print(q.groupby(['prototype_id','project','test','kind']).value.agg(['count','mean']).to_string())