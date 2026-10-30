import pandas as pd
x=pd.read_csv('records.csv'); print(x.columns.tolist()); z=x[x.project_id.eq('QP-8807')]; print(z.to_string(index=False)[:30000])