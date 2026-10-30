import pandas as pd
x=pd.read_csv('records.csv')
print(x['project'].unique())
# list panels on PL-98 prototypes, grouped
z=x[(x.project=='QP-9219') & (x.kind=='qualification')].groupby(['prototype_id','instrument','test','measured_by']).value.agg(['count','mean'])
print(z.to_string())