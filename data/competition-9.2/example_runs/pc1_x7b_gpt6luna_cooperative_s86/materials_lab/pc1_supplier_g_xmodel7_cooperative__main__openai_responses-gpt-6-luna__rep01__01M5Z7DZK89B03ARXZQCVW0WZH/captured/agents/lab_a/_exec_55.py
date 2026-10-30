import pandas as pd
x=pd.read_csv('records.csv'); x['value']=pd.to_numeric(x.value,errors='coerce')
for pid,g in x.groupby('prototype_id'):
 if pid.startswith(('p_4XN79','p_P76','p_QDC','p_MV7','p_CHA','p_5B8')):
  print(pid, g.project.iloc[0], g.measured_by.unique(), g.test.value_counts().to_dict(),g.groupby('test').value.mean().round(5).to_dict())