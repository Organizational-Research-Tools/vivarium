import pandas as pd
df = pd.read_csv('records.csv')
q = df[df.record_id.isin(['r_NZBFJQDQP5','r_NZBFJQDQP6','r_NZBFJQDQP7','r_NZBFJQDQP8','r_NZBFJQDQP9','r_NZBFJQDQPA'])]
print(q[['record_id','project','prototype_id','test','measured_by','value']].to_string())