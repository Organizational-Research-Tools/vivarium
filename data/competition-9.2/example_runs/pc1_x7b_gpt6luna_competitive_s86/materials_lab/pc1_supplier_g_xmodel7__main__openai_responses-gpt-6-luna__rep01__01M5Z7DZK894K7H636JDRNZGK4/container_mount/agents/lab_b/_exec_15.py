import pandas as pd
x=pd.read_csv('records.csv')
print(x.shape)
print(x.columns.tolist())
print(x[x['project_id'].eq('QP-9219')].groupby(['prototype_id','instrument','kind']).size().value_counts().to_dict())
print(x[(x.project_id=='QP-9219') & (x.instrument=='water')].tail(20).to_string(index=False))