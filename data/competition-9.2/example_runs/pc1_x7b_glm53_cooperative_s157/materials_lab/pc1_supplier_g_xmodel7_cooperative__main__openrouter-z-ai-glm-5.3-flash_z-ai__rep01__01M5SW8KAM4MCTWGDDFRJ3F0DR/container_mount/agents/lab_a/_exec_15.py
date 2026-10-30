import pandas as pd
df = pd.read_csv('records.csv')
for p in ['p_GM7DHPGB5W']:
    q = df[df.prototype_id==p]
    print(q[['record_id','test','measured_by','value']].to_string())
# check lab_b strength receipts exist under any prototype
q = df[df.record_id.isin(['r_P2FZ2H2S61','r_P2FZ2H2S62','r_P2FZ2H2S63','r_P2FZ2H2S64','r_P2FZ2H2S65','r_P2FZ2H2S66'])]
print(q[['record_id','project','prototype_id','test','measured_by','value']].to_string())