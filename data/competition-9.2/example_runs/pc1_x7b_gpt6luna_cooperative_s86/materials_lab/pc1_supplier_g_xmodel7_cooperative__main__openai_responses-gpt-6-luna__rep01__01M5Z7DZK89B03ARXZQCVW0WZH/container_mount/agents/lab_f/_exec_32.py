import pandas as pd
x=pd.read_csv('records.csv')
for proj in ['QP-7092','QP-6879','QP-9219']:
 d=x[x.project==proj]
 g=d.groupby(['prototype_id','test','measured_by']).agg(n=('value','size'),mean=('value','mean'))
 print('\n',proj)
 print(g.to_string())