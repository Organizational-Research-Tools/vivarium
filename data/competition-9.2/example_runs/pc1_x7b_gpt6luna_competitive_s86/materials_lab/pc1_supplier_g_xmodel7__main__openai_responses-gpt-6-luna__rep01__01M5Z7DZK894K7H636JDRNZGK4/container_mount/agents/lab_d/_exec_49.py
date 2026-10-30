import pandas as pd
x=pd.read_csv('records.csv'); x['value']=pd.to_numeric(x.value); print(x.groupby(['project','prototype_id','kind','test']).value.agg(['count','mean']).to_string())