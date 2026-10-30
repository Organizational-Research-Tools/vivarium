import pandas as pd
x=pd.read_csv('records.csv')
print(x.columns.tolist())
print(x.shape)
print(x.groupby(['project_id','instrument','kind']).size() if {'project_id','instrument','kind'}<=set(x.columns) else '')
print(x[x.get('project_id','')=='QP-7092'].to_string(index=False)[:10000])