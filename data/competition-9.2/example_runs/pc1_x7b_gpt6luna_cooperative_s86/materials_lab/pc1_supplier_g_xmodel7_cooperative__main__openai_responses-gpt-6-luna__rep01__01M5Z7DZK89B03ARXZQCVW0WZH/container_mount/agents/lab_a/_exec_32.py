import pandas as pd
x=pd.read_csv('records.csv')
print(x.columns.tolist())
print(x[x.project_id=='QP-9980'].to_string(index=False) if 'project_id' in x else x.head().to_string(index=False))