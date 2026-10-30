import pandas as pd
x=pd.read_csv('records.csv')
print(x.columns.tolist())
print(x[x.project=='QP-3617'].groupby(['prototype_id','instrument','kind']).agg(n=('value','size'),mean=('value','mean')).to_string())