import pandas as pd
x=pd.read_csv('records.csv')
q=x[x.project=='QP-8807']
print(q.groupby(['prototype_id','kind','test','measured_by']).value.agg(['count','mean']).to_string())
print('\nrecipes/protos:')
print(q.drop_duplicates('prototype_id')[['prototype_id']+list(x.columns[11:])].to_string(index=False))