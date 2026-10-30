import pandas as pd
x=pd.read_csv('records.csv')
print(x.columns.tolist())
print(x[x['project_id']=='QP-9273'].to_string(index=False)[:8000])