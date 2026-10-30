import pandas as pd
x=pd.read_csv('records.csv'); q=x[x.project=='QP-6879'];
print(q.groupby(['prototype_id','test','kind']).agg(n=('value','count'),mean=('value','mean'),owner=('measured_by','first')).to_string())
print('\nrecipes all protos:')
print(q.drop_duplicates('prototype_id')[['prototype_id']+list(x.columns[11:])].to_string(index=False))