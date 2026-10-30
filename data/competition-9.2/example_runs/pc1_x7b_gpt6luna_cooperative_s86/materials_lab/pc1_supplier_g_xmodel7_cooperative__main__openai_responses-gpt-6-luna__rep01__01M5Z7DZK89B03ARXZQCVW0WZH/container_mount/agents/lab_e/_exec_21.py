import pandas as pd
x=pd.read_csv('records.csv')
print(x.groupby(['project','prototype_id','instrument','test']).size().unstack(fill_value=0).to_string())