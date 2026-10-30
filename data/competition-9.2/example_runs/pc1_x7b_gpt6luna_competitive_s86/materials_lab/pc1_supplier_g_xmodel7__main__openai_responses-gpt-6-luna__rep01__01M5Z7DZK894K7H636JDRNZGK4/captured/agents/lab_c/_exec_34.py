import pandas as pd
r=pd.read_csv('records.csv')
x=r[r.project.eq('QP-6879')]
print(x.tail(60).to_string(index=False))