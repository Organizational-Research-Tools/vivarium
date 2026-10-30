import pandas as pd
x=pd.read_csv('records.csv'); mods=x.columns[11:]
print('unique prototypes',x.prototype_id.nunique(),'projects',x.project.value_counts().to_dict(),'tests',x.groupby(['project','instrument']).size().to_dict())
print(x.groupby(['prototype_id','project','instrument','measured_by']).size().unstack(fill_value=0).to_string())
print('\nrecipes per project');
for p,g in x.groupby('project'):
 print('\n',p)
 print(g.drop_duplicates('prototype_id')[['prototype_id']+list(mods)].to_string(index=False))