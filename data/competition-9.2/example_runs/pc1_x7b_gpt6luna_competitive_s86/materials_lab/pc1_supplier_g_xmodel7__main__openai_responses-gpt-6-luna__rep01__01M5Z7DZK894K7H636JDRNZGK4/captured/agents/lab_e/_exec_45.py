import pandas as pd
x=pd.read_csv('records.csv')
for pid in ['p_K6ZM59ZMJT','p_K6ZM59ZMJM','p_EGTGJGD3PY','p_CEYHT8P45J','p_Z2HJ9VEQ12','p_RZFQB2P3KJ']:
 y=x[x.prototype_id==pid]
 print('\n',pid, y[['kind','instrument','test','value','measured_by']].to_string(index=False))