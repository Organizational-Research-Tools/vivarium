import pandas as pd
x=pd.read_csv('records.csv')
print(x.columns.tolist())
print(x[x.project_id.eq('QP-7092')].head().to_string(index=False))