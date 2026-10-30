import pandas as pd
D=pd.read_csv('records.csv')
print('projects',D.project.unique())
print(D.groupby(['project','prototype_id']).agg(n=('record_id','size'),tests=('test','nunique'),proto=('prototype_id','first')).tail(30).to_string())