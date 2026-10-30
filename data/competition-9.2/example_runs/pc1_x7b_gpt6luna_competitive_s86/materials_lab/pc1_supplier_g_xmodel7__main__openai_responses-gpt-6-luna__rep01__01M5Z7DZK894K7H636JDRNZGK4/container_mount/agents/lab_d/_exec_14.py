import pandas as pd
x=pd.read_csv('records.csv')
print(x.shape)
print(x['kind'].value_counts()); print(x.groupby(['project','measured_by','test','kind']).size().to_string())
print(x[x['project']=='QP-9219'].groupby(['measured_by','test','kind']).size().to_string())