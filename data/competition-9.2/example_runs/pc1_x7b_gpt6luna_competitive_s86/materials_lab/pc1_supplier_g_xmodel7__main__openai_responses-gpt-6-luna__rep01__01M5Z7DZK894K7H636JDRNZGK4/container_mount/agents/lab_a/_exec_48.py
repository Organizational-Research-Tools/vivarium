import pandas as pd
x=pd.read_csv('records.csv')
for pid in ['p_30SJBPRZKP','p_2YHYS3GPHP','p_NBE0']:
 q=x[x.prototype_id.astype(str).str.contains(pid, regex=False)]
 print('\n',pid, len(q)); print(q[['project','prototype_id','record_id','kind','test','value','measured_by']].to_string(index=False));print(q.drop_duplicates('prototype_id').iloc[:1,11:].to_dict('records'))
