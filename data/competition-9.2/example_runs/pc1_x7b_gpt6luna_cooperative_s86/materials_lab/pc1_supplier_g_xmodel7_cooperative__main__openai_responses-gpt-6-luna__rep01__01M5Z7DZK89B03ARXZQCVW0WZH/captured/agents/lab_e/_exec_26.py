import pandas as pd
x=pd.read_csv('records.csv')
print(x.shape)
print(x.groupby(['project','prototype_id','instrument'])['value'].mean().unstack().tail(20).to_string())