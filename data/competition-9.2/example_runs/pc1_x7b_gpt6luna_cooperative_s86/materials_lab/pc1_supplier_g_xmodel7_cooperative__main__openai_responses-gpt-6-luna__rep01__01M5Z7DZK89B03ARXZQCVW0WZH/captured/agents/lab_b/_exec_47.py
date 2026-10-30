import pandas as pd
x=pd.read_csv('records.csv')
print(x.groupby(['project','prototype_id','instrument']).value.mean().unstack().to_string())