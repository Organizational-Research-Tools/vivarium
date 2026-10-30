import pandas as pd
x=pd.read_csv('records.csv')
d=x[x.project.eq('QP-9273')]
print(d.to_string(index=False))