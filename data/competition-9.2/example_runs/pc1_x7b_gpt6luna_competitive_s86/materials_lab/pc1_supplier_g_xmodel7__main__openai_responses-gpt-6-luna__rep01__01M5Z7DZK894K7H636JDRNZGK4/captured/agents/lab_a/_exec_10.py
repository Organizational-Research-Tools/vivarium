import pandas as pd
x=pd.read_csv('records.csv'); print('projects',x.project.value_counts().to_dict()); print('kinds',x.kind.value_counts().to_dict()); print(x.groupby(['project','kind','instrument']).size().to_string())
print('\nunique prototypes by project',x.groupby('project').prototype_id.nunique().to_dict())
print('\nfull panel recipes by project')
q=x[x.kind=='qualification'].groupby(['project','prototype_id']).test.nunique(); print(q[q==3].to_string())