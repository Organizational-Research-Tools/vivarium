import pandas as pd
x=pd.read_csv('records.csv')
print('rows',len(x),'projects',x.project.unique())
print(x.groupby(['project','prototype_id','test']).value.mean().unstack().to_string())