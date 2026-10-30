import pandas as pd
x=pd.read_csv('records.csv'); q=x[x.project=='QP-6879'];
print(q.groupby(['prototype_id','test','kind']).agg(n=('value','size'),mean=('value','mean'),owner=('measured_by','first')).to_string())