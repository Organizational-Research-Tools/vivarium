import pandas as pd
x=pd.read_csv('records.csv')
print(x.columns.tolist())
for p in ['p_EGTGJGD3PY','p_K6ZM59ZMJT','p_K6ZM59ZMJM','p_K6ZM59ZMJP','p_K6ZM59ZMJR']:
 y=x[x.prototype_id==p]
 print('\n',p, 'rows',len(y))
 print(y[['record_id','project_id','kind','instrument','value','measured_by']].to_string(index=False))
 if not y.empty: print(y.iloc[0][[c for c in x.columns if c.startswith('m')]].to_dict())