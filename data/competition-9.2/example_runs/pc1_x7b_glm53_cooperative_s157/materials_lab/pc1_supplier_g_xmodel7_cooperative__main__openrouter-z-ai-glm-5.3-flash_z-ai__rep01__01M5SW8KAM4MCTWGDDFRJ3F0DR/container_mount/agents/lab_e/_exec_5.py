import pandas as pd
df = pd.read_csv('records.csv')
x = df[df['binder_system']=='27X']
print(x[['prototype_id','project','test','kind','value','measured_by']].to_string())
print(x.groupby(['project','prototype_id','test'])['value'].agg(['count','mean']).to_string())